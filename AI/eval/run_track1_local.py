"""트랙 1(패턴 규칙 미적용 vs 적용)을 학교 서버의 Qwen3.8-27B(4bit)로 돌린다.

용도: 실발화 227(처음엔 232)을 학교 서버 GPU에서 푼다. 2026-10-21 트랙 1 사전 실험(학습 없이 프롬프트에
      패턴 규칙을 넣는 방식)에 썼고, --adapter로 중간발표의 모델별 실발화 227 숫자도 냈다.
      팀 결정(10-21)으로 트랙 1 본실험은 '패턴 데이터로 학습' 방식이 되어, 본실험 채점은 run_raw_test_local.py가 맡는다.

- 프롬프트 만들기 · 답 읽기 · 채점은 팀원의 run_track1.py를 그대로 불러다 쓴다.
  여기서 새로 짠 부분은 "모델에게 묻기" 하나뿐이다 (원본은 vLLM 서버에 HTTP로 묻고, 여기서는 GPU의 모델에 직접 묻는다).
- 모델을 한 번 올려 base · pattern 두 모드를 연달아 푼다. 모드마다 결과 파일이 하나씩 생긴다.
- GPU 1장:  python run_track1_local.py --kit 트랙1폴더 --out_dir 결과폴더
- GPU 3장:  accelerate launch --num_processes 3 run_track1_local.py ... (문제를 3등분해 나눠 푼다)
- 경로 설정은 AI/.env에서 읽는다 (AI/.env.example 참고).
"""
import argparse
import importlib
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

EVAL_DIR = Path(__file__).resolve().parent           # AI/eval
AI_DIR = EVAL_DIR.parent                             # AI

# AI/.env에서 경로를 읽는다. torch·transformers를 불러오기 전에 해야 HF_HOME과 캐시 위치가 적용된다.
ENV_FILE = AI_DIR / ".env"
if not ENV_FILE.exists():
    sys.exit("AI/.env가 없다. AI/.env.example을 복사해 AI/.env를 만들고 경로를 채운다.")
load_dotenv(ENV_FILE, override=True)
_missing = [k for k in ("HF_HOME", "LOCAL_ROOT") if not os.environ.get(k)]
if _missing:
    sys.exit(f"AI/.env에 값이 비어 있다: {', '.join(_missing)}")
LOCAL_ROOT = Path(os.environ["LOCAL_ROOT"])

# NAS는 작은 파일 쓰기가 매우 느리므로, 커널 컴파일 캐시는 로컬 디스크에 둔다.
os.environ.setdefault("TRITON_CACHE_DIR", str(LOCAL_ROOT / "triton-cache"))
os.environ.setdefault("TORCHINDUCTOR_CACHE_DIR", str(LOCAL_ROOT / "inductor-cache"))

import torch
import torch.distributed as dist
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True, help="run_track1.py와 testset_v0.jsonl이 있는 폴더")
    p.add_argument("--script", default="run_track1", help="키트 안의 실행 스크립트 이름 (.py 제외). 예: run_track1_v01")
    p.add_argument("--data", default="testset_v0.jsonl", help="키트 안의 시험지 파일. 예: testset_v0_1.jsonl")
    p.add_argument("--out_dir", required=True, help="모드별 결과 jsonl을 둘 폴더 (results_<모드>.jsonl)")
    p.add_argument("--model", default="Qwen/Qwen3.8-27B")
    p.add_argument("--adapter", default=None, help="LoRA 어댑터 폴더. 없으면 학습 전 모델")
    p.add_argument("--modes", nargs="+", default=["base", "pattern"], choices=["base", "pattern"])
    p.add_argument("--dasan_input", default="stt", choices=["stt", "gt"],
                   help="gt면 다산콜 12건을 깨끗한 정답문으로 입력 (원본 --dasan-input과 같음)")
    p.add_argument("--max_new_tokens", type=int, default=30)    # 원본 max_tokens와 같게
    p.add_argument("--limit", type=int, default=0, help="앞에서 N문제만 (시험 실행용)")
    return p.parse_args()


def load_kit(kit, script):
    """원본 트랙 1 스크립트를 모듈로 불러온다. 파일은 고치지 않고, __pycache__도 만들지 않는다."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(kit).resolve()))
    return importlib.import_module(script)


def ask(model, tok, messages, a, device):
    """원본에서 HTTP 요청 부분만 GPU 생성으로 바꾼 것. 원본처럼 temperature 0, 비추론 모드."""
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                     enable_thinking=False)
    ids = tok(prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=a.max_new_tokens, do_sample=False)
    return tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)


def main():
    a = parse_args()
    # accelerate launch로 띄우면 RANK·WORLD_SIZE가 정해진다. 그냥 python으로 띄우면 GPU 1장(0번).
    rank, world = int(os.environ.get("RANK", 0)), int(os.environ.get("WORLD_SIZE", 1))
    local_rank = int(os.environ.get("LOCAL_RANK", 0))
    is_main = rank == 0
    if world > 1:
        dist.init_process_group("gloo")   # 결과(파이썬 객체)만 모으면 되므로 CPU 통신으로 충분

    t1 = load_kit(a.kit, a.script)
    with open(Path(a.kit) / a.data, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    if a.limit:
        rows = rows[:a.limit]
    mine = rows[rank::world]              # 문제를 GPU 수만큼 번갈아 나눠 맡는다
    if is_main:
        print(f"[data] {a.data} {len(rows)}문제 × 모드 {a.modes}, 스크립트 {a.script}, GPU {world}장 (adapter {a.adapter or '없음'}, "
              f"dasan_input {a.dasan_input})", flush=True)

    # 학습과 같은 4bit(NF4) 설정으로 모델을 이 프로세스의 GPU 한 장에 올린다.
    tok = AutoTokenizer.from_pretrained(a.model)
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(a.model, quantization_config=bnb,
                                                 device_map={"": local_rank}, dtype=torch.bfloat16)
    if a.adapter:   # 학습한 모델로 잴 때: 4bit 원본 위에 LoRA 어댑터를 얹는다
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, a.adapter)
    model.eval()

    out_files = []
    for mode in a.modes:
        res, t0 = [], time.time()
        for i, x in enumerate(mine, 1):
            msgs = t1.build_messages(x, mode, a.dasan_input)
            try:
                raw = ask(model, tok, msgs, a, local_rank)
            except Exception as e:  # noqa  원본처럼 실패도 한 행으로 남긴다
                raw = "ERROR: " + str(e)
            res.append({**x, "mode": mode, "raw": raw, "pred": t1.parse_pred(raw)})
            if is_main and i % 20 == 0:
                print(f"[gen] {mode} {i}/{len(mine)}  {time.time()-t0:.0f}s 경과", flush=True)

        if world > 1:   # 모든 GPU의 결과를 0번으로 모은다
            gathered = [None] * world
            dist.all_gather_object(gathered, res)
            res = [r for part in gathered for r in part]
        if is_main:
            order = {x["id"]: k for k, x in enumerate(rows)}
            res.sort(key=lambda r: order[r["id"]])   # 원래 문제 순서로
            out = Path(a.out_dir) / f"results_{mode}.jsonl"
            out.parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                for r in res:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            out_files.append(str(out))
            print(f"[mode] {mode} 끝: {time.time()-t0:.0f}s -> {out}", flush=True)

    if is_main:   # 원본 채점: 그룹별 정확도 + 패턴 규칙으로 뒤집힌 사례
        t1.score(out_files)
        print("\n[done]", flush=True)
    if world > 1:
        dist.destroy_process_group()


if __name__ == "__main__":
    main()
