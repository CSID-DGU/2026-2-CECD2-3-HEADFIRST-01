"""노인 raw test 62(트랙 1 본실험 시험지)를 학교 서버의 Qwen3.8-27B(4bit)로 풀고 팀원의 evaluate_raw.py로 채점한다.

용도: 트랙 1 본실험(원본 데이터 학습 R vs 패턴 데이터 학습 P)의 시험지 채점 (2026-10-21).
      중간발표의 raw test 62 숫자(학습 전, R, P, v3, v3.1)를 이 스크립트로 냈다.

- 입력은 SFT 형식(raw_노인_test.jsonl)이다. system + user만 주고, assistant(정답)는 채점용으로 둔다.
- 결과 줄 형식은 evaluate_raw.py가 읽는 형식(dialogue_id, gold, pred)에 raw(모델 원문)를 더한 것이다.
- 모델을 한 번 올려 학습 전 상태로 풀고, --adapter로 준 어댑터를 차례로 얹어 같은 문제를 다시 푼다.
- 실행:  python run_raw_test_local.py --kit raw_elderly_v1폴더 --out_dir 결과폴더 --adapter 이름=어댑터폴더 ...
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
_missing = [k for k in ("HF_HOME", "LOCAL_ROOT") if not os.environ.get(k)]
if _missing:
    sys.exit(f"AI/.env에 값이 비어 있다: {', '.join(_missing)}")
LOCAL_ROOT = Path(os.environ["LOCAL_ROOT"])

# NAS는 작은 파일 쓰기가 매우 느리므로, 커널 컴파일 캐시는 로컬 디스크에 둔다.
os.environ.setdefault("TRITON_CACHE_DIR", str(LOCAL_ROOT / "triton-cache"))
os.environ.setdefault("TORCHINDUCTOR_CACHE_DIR", str(LOCAL_ROOT / "inductor-cache"))

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True, help="evaluate_raw.py와 raw_노인_test.jsonl이 있는 폴더")
    p.add_argument("--data", default="raw_노인_test.jsonl")
    p.add_argument("--out_dir", required=True, help="결과 jsonl을 둘 폴더")
    p.add_argument("--model", default="Qwen/Qwen3.8-27B")
    p.add_argument("--adapter", action="append", default=[], help="이름=어댑터폴더. 여러 번 줄 수 있다")
    p.add_argument("--skip_base", action="store_true", help="학습 전 풀이를 건너뛴다 (이미 결과가 있을 때)")
    p.add_argument("--max_new_tokens", type=int, default=200)
    p.add_argument("--limit", type=int, default=0, help="앞에서 N문제만 (시험 실행용)")
    return p.parse_args()


def load_kit(kit):
    """팀원의 채점 스크립트를 모듈로 불러온다. 파일은 고치지 않고, __pycache__도 만들지 않는다."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(kit).resolve()))
    import evaluate_raw
    return evaluate_raw


def ask(model, tok, messages, a):
    """temperature 0(가장 그럴듯한 답 하나), 비추론 모드. 학습 때와 같은 대화 형식이다."""
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                     enable_thinking=False)
    ids = tok(prompt, return_tensors="pt").to(0)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=a.max_new_tokens, do_sample=False)
    return tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)


def solve(model, tok, rows, a, label, out):
    """문제를 풀어 evaluate_raw.py 형식으로 저장한다. JSON으로 못 읽은 답(파싱 실패)은 pred를 빈 문자열로 둔다."""
    t0 = time.time()
    fails = 0
    with open(out, "w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            raw = ask(model, tok, r["messages"][:2], a)
            try:
                pred = json.dumps(json.loads(raw), ensure_ascii=False)
            except Exception:
                pred, fails = "", fails + 1
            f.write(json.dumps({"dialogue_id": r["dialogue_id"], "pattern": r.get("pattern", ""),
                                "category": ["노인"], "utterance": r["messages"][1]["content"].split("[마지막 USER 발화]")[-1].strip(),
                                "gold": r["messages"][2]["content"], "pred": pred, "raw": raw},
                               ensure_ascii=False) + "\n")
            if i % 10 == 0:
                print(f"[gen] {label} {i}/{len(rows)}  {time.time()-t0:.0f}s 경과", flush=True)
    print(f"[{label}] 끝: {time.time()-t0:.0f}s, 파싱 실패 {fails} -> {out}", flush=True)
    return out


def main():
    a = parse_args()
    kit = load_kit(a.kit)
    with open(Path(a.kit) / a.data, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    if a.limit:
        rows = rows[:a.limit]
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    adapters = [s.split("=", 1) for s in a.adapter]
    print(f"[data] {a.data} {len(rows)}문제, 어댑터 {[n for n, _ in adapters] or '없음'}", flush=True)

    # 학습과 같은 4bit(NF4) 설정으로 모델을 GPU 0번에 올린다.
    tok = AutoTokenizer.from_pretrained(a.model)
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(a.model, quantization_config=bnb,
                                                 device_map={"": 0}, dtype=torch.bfloat16)
    model.eval()

    outs = []
    if not a.skip_base:
        outs.append(("base", solve(model, tok, rows, a, "학습 전", out_dir / "pred_base.jsonl")))
    if adapters:   # 같은 4bit 원본 위에 어댑터를 하나씩 바꿔 끼우며 다시 푼다
        from peft import PeftModel
        first_name, first_path = adapters[0]
        model = PeftModel.from_pretrained(model, first_path, adapter_name=first_name)
        for name, path in adapters[1:]:
            model.load_adapter(path, adapter_name=name)
        model.eval()
        for name, _ in adapters:
            model.set_adapter(name)
            outs.append((name, solve(model, tok, rows, a, name, out_dir / f"pred_{name}.jsonl")))

    for name, out in outs:   # 원본 채점: JGA · slot F1 · act별 P/R/F1 · macro-F1 · 셀별 + 다수결 베이스라인
        print(f"\n===== {name}", flush=True)
        kit.cmd_score(argparse.Namespace(pred=str(out), track="노인"))
    print("\n[done]", flush=True)


if __name__ == "__main__":
    main()
