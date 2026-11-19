"""하드 테스트셋(dev 100 / test 200)을 farm7 GPU의 Qwen3.8-27B(4bit nf4)로 풀어, score_hard.py가 읽는 예측 파일을 만든다.

용도: 최종 발표용 하드 테스트셋 평가를 vLLM 서버 없이 GPU에 직접 올려서 할 때 쓴다.
      학습 전 모델과 어댑터(예: A′ v3.1)의 예측 파일을 만들어 팀원의 score_hard.py로 채점받는다.

- run_hardset_vllm.py의 transformers + nf4판이다. 입력(*_sft.jsonl의 system + user), 출력 형식(*_eval_turns.jsonl + "pred")이 같다.
- 모델 설정과 답 만들기는 run_raw_test_local.py와 같다: 학습과 같은 4bit nf4, temperature 0(do_sample=False), 비추론 모드.
- 모델을 한 번 올려 학습 전 상태로 풀고, --adapter로 준 어댑터를 얹어 같은 문제를 다시 푼다.
- GPU 여러 장: 프로세스마다 CUDA_VISIBLE_DEVICES와 --shard i --nshards N을 주고, 끝나면 --merge로 합친다.
    CUDA_VISIBLE_DEVICES=0 python run_hardset_local.py --kit 폴더 --out_dir 결과 --adapter Aprime=어댑터 --shard 0 --nshards 3 &
    ... (1, 2도 같게)
    python run_hardset_local.py --kit 폴더 --out_dir 결과 --adapter Aprime=어댑터 --nshards 3 --merge
- 경로 설정은 AI/.env에서 읽는다 (AI/.env.example 참고).
"""
import argparse
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
LOCAL_ROOT = Path(os.environ["LOCAL_ROOT"])
os.environ.setdefault("TRITON_CACHE_DIR", str(LOCAL_ROOT / "triton-cache"))
os.environ.setdefault("TORCHINDUCTOR_CACHE_DIR", str(LOCAL_ROOT / "inductor-cache"))

FILES = {"dev": ("hard_dev_sft.jsonl", "hard_dev_eval_turns.jsonl"),
         "test": ("test/hard_test_sft.jsonl", "test/hard_test_eval_turns.jsonl")}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True, help="hardset_eval_handoff_20261118 폴더")
    p.add_argument("--splits", nargs="+", default=["dev", "test"], choices=list(FILES))
    p.add_argument("--out_dir", required=True)
    p.add_argument("--model", default="Qwen/Qwen3.8-27B")
    p.add_argument("--adapter", action="append", default=[], help="이름=어댑터폴더. 여러 번 줄 수 있다")
    p.add_argument("--max_new_tokens", type=int, default=1024)   # run_hardset_vllm.py와 같게
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--nshards", type=int, default=1)
    p.add_argument("--merge", action="store_true", help="조각 파일을 합쳐 pred_<split>_<이름>.jsonl을 만든다")
    return p.parse_args()


def load_split(kit, split):
    sft_name, turns_name = FILES[split]
    sft = [json.loads(l) for l in (Path(kit) / sft_name).open(encoding="utf-8") if l.strip()]
    turns = [json.loads(l) for l in (Path(kit) / turns_name).open(encoding="utf-8") if l.strip()]
    assert len(sft) == len(turns) and all(s["dialogue_id"] == t["dialogue_id"] for s, t in zip(sft, turns))
    return sft, turns


def names(a):
    return ["untrained"] + [s.split("=", 1)[0] for s in a.adapter]


def merge(a):
    out_dir = Path(a.out_dir)
    for split in a.splits:
        _, turns = load_split(a.kit, split)
        for name in names(a):
            raws = {}
            for i in range(a.nshards):
                for l in (out_dir / f"part_{split}_{name}_{i}.jsonl").open(encoding="utf-8"):
                    r = json.loads(l)
                    raws[r["dialogue_id"]] = r["raw"]
            assert len(raws) == len(turns), f"{split} {name}: {len(raws)}/{len(turns)}"
            with open(out_dir / f"pred_{split}_{name}.jsonl", "w", encoding="utf-8") as f:
                for t in turns:
                    raw = raws[t["dialogue_id"]]
                    f.write(json.dumps({**t, "pred": raw, "raw": raw, "model": f"{name} (transformers nf4)"},
                                       ensure_ascii=False) + "\n")
            print(f"[merge] {split} {name}: {len(turns)}문제 -> pred_{split}_{name}.jsonl", flush=True)


def main():
    a = parse_args()
    if a.merge:
        return merge(a)

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = {}   # split -> 이 조각이 풀 (sft, turn) 목록
    for split in a.splits:
        sft, turns = load_split(a.kit, split)
        jobs[split] = [x for i, x in enumerate(zip(sft, turns)) if i % a.nshards == a.shard]
    print(f"[data] 조각 {a.shard}/{a.nshards}: " + ", ".join(f"{s} {len(v)}문제" for s, v in jobs.items()), flush=True)

    # 학습과 같은 4bit(NF4) 설정으로 모델을 이 프로세스의 GPU 0번(CUDA_VISIBLE_DEVICES로 고른 GPU)에 올린다.
    tok = AutoTokenizer.from_pretrained(a.model)
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(a.model, quantization_config=bnb,
                                                 device_map={"": 0}, dtype=torch.bfloat16)
    model.eval()

    def ask(messages):
        """temperature 0(가장 그럴듯한 답 하나), 비추론 모드. 학습 때와 같은 대화 형식이다."""
        prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                         enable_thinking=False)
        ids = tok(prompt, return_tensors="pt").to(0)
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=a.max_new_tokens, do_sample=False)
        return tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)

    def solve(name):
        for split, items in jobs.items():
            t0 = time.time()
            with open(out_dir / f"part_{split}_{name}_{a.shard}.jsonl", "w", encoding="utf-8") as f:
                for i, (s, t) in enumerate(items, 1):
                    f.write(json.dumps({"dialogue_id": t["dialogue_id"], "raw": ask(s["messages"][:2])},
                                       ensure_ascii=False) + "\n")
                    f.flush()
                    if i % 10 == 0:
                        print(f"[gen] {name} {split} {i}/{len(items)}  {time.time()-t0:.0f}s 경과", flush=True)
            print(f"[{name}] {split} 끝: {time.time()-t0:.0f}s", flush=True)

    solve("untrained")
    if a.adapter:   # 같은 4bit 원본 위에 어댑터를 하나씩 바꿔 끼우며 다시 푼다
        from peft import PeftModel
        pairs = [s.split("=", 1) for s in a.adapter]
        model = PeftModel.from_pretrained(model, pairs[0][1], adapter_name=pairs[0][0])
        for name, path in pairs[1:]:
            model.load_adapter(path, adapter_name=name)
        model.eval()
        for name, _ in pairs:
            model.set_adapter(name)
            solve(name)
    print("[done]", flush=True)


if __name__ == "__main__":
    main()
