"""Qwen3.8-27B QLoRA 학습 스크립트.

- 모델 원본을 4bit로 압축해 GPU 한 장에 올리고(QLoRA의 Q), LoRA 어댑터만 학습한다.
- GPU 1장:  python train_qlora.py --run_name test
- GPU 3장:  accelerate launch --num_processes 3 train_qlora.py --run_name test
- 데이터는 messages(system/user/assistant) 형식 jsonl. 데이터가 바뀌면 --train/--valid 경로만 바꾼다.
- 정답(assistant) 부분에서만 손실을 계산한다(completion-only loss).
- 경로 설정은 AI/.env에서 읽는다 (AI/.env.example 참고).
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

TRAIN_DIR = Path(__file__).resolve().parent          # AI/train
AI_DIR = TRAIN_DIR.parent                            # AI
DATA_DIR = AI_DIR / "data"                           # 레포 안의 데이터 폴더 (사람마다 같음)

# AI/.env에서 경로를 읽는다. torch·transformers를 불러오기 전에 해야 HF_HOME과 캐시 위치가 적용된다.
ENV_FILE = AI_DIR / ".env"
if not ENV_FILE.exists():
    sys.exit("AI/.env가 없다. AI/.env.example을 복사해 AI/.env를 만들고 경로를 채운다.")
load_dotenv(ENV_FILE, override=True)
_missing = [k for k in ("HF_HOME", "LOCAL_ROOT", "RUNS_ARCHIVE") if not os.environ.get(k)]
if _missing:
    sys.exit(f"AI/.env에 값이 비어 있다: {', '.join(_missing)}")
LOCAL_ROOT = Path(os.environ["LOCAL_ROOT"])
RUNS_ARCHIVE = Path(os.environ["RUNS_ARCHIVE"])

# NAS는 작은 파일 쓰기가 매우 느리므로, 커널 컴파일 캐시는 로컬 디스크에 둔다.
os.environ.setdefault("TRITON_CACHE_DIR", str(LOCAL_ROOT / "triton-cache"))
os.environ.setdefault("TORCHINDUCTOR_CACHE_DIR", str(LOCAL_ROOT / "inductor-cache"))
os.environ.setdefault("HF_DATASETS_CACHE", str(LOCAL_ROOT / "hf-datasets"))

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainerCallback
from trl import SFTConfig, SFTTrainer

# Qwen3.8의 선형층 중 LoRA를 붙일 곳: 일반 어텐션 + Gated DeltaNet + FFN
TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",          # 일반 어텐션 (16개 층)
    "in_proj_qkv", "in_proj_z", "out_proj",          # Gated DeltaNet (48개 층)
    "gate_proj", "up_proj", "down_proj",             # FFN (64개 층 전부)
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", default="Qwen/Qwen3.8-27B")
    p.add_argument("--train", default=f"{DATA_DIR}/sft_train.jsonl")
    p.add_argument("--valid", default=f"{DATA_DIR}/sft_valid.jsonl")
    p.add_argument("--run_name", required=True)
    p.add_argument("--output_root", default=str(LOCAL_ROOT / "runs"))   # 학습 중 결과는 로컬에
    p.add_argument("--archive", action="store_true",
                   help="학습 후 최종 어댑터를 RUNS_ARCHIVE로 복사 (NAS가 느리면 수 분 걸릴 수 있음)")
    p.add_argument("--max_train", type=int, default=0, help="0이면 전체, 테스트 때는 일부만")
    p.add_argument("--max_valid", type=int, default=0)
    p.add_argument("--epochs", type=float, default=3)
    p.add_argument("--max_steps", type=int, default=-1, help="-1이면 epochs 기준")
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--grad_accum", type=int, default=4)
    p.add_argument("--max_len", type=int, default=1024)
    p.add_argument("--lora_r", type=int, default=16)
    p.add_argument("--lora_alpha", type=int, default=32)
    p.add_argument("--lora_dropout", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--eval_every", default="epoch", help="'epoch' 또는 스텝 수")
    p.add_argument("--sample_generate", type=int, default=0, help="학습 후 검증 데이터 몇 건으로 생성해 볼지")
    return p.parse_args()


def load_jsonl(path, limit, tok):
    """messages 형식 한 건을 prompt(입력)와 completion(정답)으로 나눈다.

    prompt는 Qwen 대화 템플릿을 thinking 끔 상태로 적용한 문자열이고,
    completion은 정답 JSON + 끝 표시(<|im_end|>)다. 서비스할 때도 thinking을 끈 같은 형식으로 호출해야 한다.
    데이터 형식이 바뀌면 이 함수만 고치면 된다.
    """
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            msgs = r["messages"]
            assert msgs[-1]["role"] == "assistant", "마지막 메시지가 정답(assistant)이어야 한다"
            prompt = tok.apply_chat_template(msgs[:-1], tokenize=False, add_generation_prompt=True,
                                             enable_thinking=False)
            rows.append({"prompt": prompt, "completion": msgs[-1]["content"] + "<|im_end|>",
                         "pattern": r.get("pattern", "")})
            if limit and len(rows) >= limit:
                break
    return Dataset.from_list(rows)


class MemoryTimeCallback(TrainerCallback):
    """로그를 찍을 때마다 GPU 최대 메모리와 스텝당 시간을 함께 기록한다."""

    def __init__(self):
        self.t = time.time()

    def on_log(self, args, state, control, logs=None, **kw):
        if logs is None or not torch.cuda.is_available():
            return
        logs["gpu_peak_gib"] = round(torch.cuda.max_memory_allocated() / 1024**3, 2)
        logs["sec_since_last_log"] = round(time.time() - self.t, 1)
        self.t = time.time()


def main():
    a = parse_args()
    local_rank = int(os.environ.get("LOCAL_RANK", 0))   # GPU 3장이면 0,1,2 각각 다른 프로세스
    is_main = local_rank == 0
    out_dir = os.path.join(a.output_root, a.run_name)

    tok = AutoTokenizer.from_pretrained(a.model)
    train_ds = load_jsonl(a.train, a.max_train, tok)
    valid_ds = load_jsonl(a.valid, a.max_valid, tok)
    if is_main:
        print(f"[data] train {len(train_ds)} / valid {len(valid_ds)}", flush=True)

    # 1) 모델 원본을 4bit(NF4)로 압축해 이 프로세스의 GPU 한 장에 올린다.
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(a.model, quantization_config=bnb,
                                                 device_map={"": local_rank}, dtype=torch.bfloat16)
    model.config.use_cache = False          # 학습 중에는 생성용 캐시가 필요 없다
    model.enable_input_require_grads()      # gradient checkpointing + 얼린 임베딩 조합에 필요

    # 2) LoRA 어댑터를 붙인다. 원본은 얼리고 어댑터만 학습된다.
    lora = LoraConfig(r=a.lora_r, lora_alpha=a.lora_alpha, lora_dropout=a.lora_dropout,
                      target_modules=TARGET_MODULES, task_type="CAUSAL_LM")
    model = get_peft_model(model, lora)
    if is_main:
        model.print_trainable_parameters()
        print(f"[mem] after model+LoRA: {torch.cuda.memory_allocated(local_rank)/1024**3:.2f} GiB", flush=True)

    eval_steps = None if a.eval_every == "epoch" else int(a.eval_every)
    cfg = SFTConfig(
        output_dir=out_dir,
        run_name=a.run_name,
        num_train_epochs=a.epochs,
        max_steps=a.max_steps,
        per_device_train_batch_size=a.batch,
        per_device_eval_batch_size=a.batch,
        gradient_accumulation_steps=a.grad_accum,
        learning_rate=a.lr,
        lr_scheduler_type="cosine",
        warmup_steps=0.03,                # 0~1 소수는 전체 스텝 대비 비율 (transformers 5)
        bf16=True,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        max_length=a.max_len,
        completion_only_loss=True,        # 정답 부분에서만 손실 계산
        packing=False,
        logging_steps=1,
        eval_strategy="epoch" if eval_steps is None else "steps",
        eval_steps=eval_steps,
        save_strategy="epoch" if eval_steps is None else "steps",
        save_steps=eval_steps,
        save_total_limit=2,
        report_to="none",
        dataloader_num_workers=2,         # CPU 한도 8코어
        dataset_num_proc=4,
        ddp_find_unused_parameters=False,
        seed=a.seed,
    )
    trainer = SFTTrainer(model=model, args=cfg, train_dataset=train_ds, eval_dataset=valid_ds,
                         processing_class=tok, callbacks=[MemoryTimeCallback()])

    if is_main:   # 실제로 모델에 들어가는 첫 데이터와 채점 구간을 눈으로 확인
        ex = trainer.train_dataset[0]
        ids, labels = ex["input_ids"], ex.get("labels")   # TRL은 채점 제외 토큰을 labels=-100으로 표시
        if labels is None:
            print("[check] labels 없음: 전체 토큰을 채점하고 있을 수 있음!", flush=True)
        else:
            scored = [t for t, l in zip(ids, labels) if l != -100]
            print(f"[check] tokens {len(ids)}, scored tokens {len(scored)}", flush=True)
            print("[check] scored text:", repr(tok.decode(scored)), flush=True)

    t0 = time.time()
    trainer.train()
    if is_main:
        print(f"[train] done in {time.time()-t0:.0f}s", flush=True)
        trainer.save_model(out_dir)          # 어댑터만 저장 (원본 55GB는 저장 안 함)
        print(f"[save] adapter -> {out_dir}", flush=True)
        if a.archive:                        # 중간 저장본(checkpoint-*)은 빼고 최종 결과만 보관
            dst = RUNS_ARCHIVE / a.run_name
            shutil.copytree(out_dir, dst, ignore=shutil.ignore_patterns("checkpoint-*"), dirs_exist_ok=True)
            print(f"[archive] -> {dst}", flush=True)

    metrics = trainer.evaluate()
    if is_main:
        print(f"[eval] {metrics}", flush=True)

    if is_main and a.sample_generate:
        model.eval()
        model.config.use_cache = True
        for i in range(min(a.sample_generate, len(valid_ds))):
            ex = valid_ds[i]
            ids = tok(ex["prompt"], return_tensors="pt").to(local_rank)
            with torch.no_grad():
                out = model.generate(**ids, max_new_tokens=128, do_sample=False)
            pred = tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)
            print(f"[gen {i}] pattern {ex['pattern']}\n  pred: {pred}\n  gold: {ex['completion'][:-len('<|im_end|>')]}", flush=True)
    if is_main:
        print("[done]", flush=True)
    if torch.distributed.is_initialized():   # GPU 3장 실행 시 프로세스 간 통신을 깔끔하게 종료
        torch.distributed.destroy_process_group()


if __name__ == "__main__":
    main()
