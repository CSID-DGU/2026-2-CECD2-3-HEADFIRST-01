"""노인 실발화 평가셋(70건)을 학교 서버의 Qwen3.8-27B(4bit)로 학습 전 · 학습 후 연달아 잰다.

용도: 노인 실발화 70건으로 학습 전 vs 학습 후(v3, v3.1)를 비교했다 (2026-10-21~22, 중간발표 숫자).
      트랙 1 R 모델은 학습 데이터에 이 70건 중 47건이 들어 있어서 이 평가에 쓰지 않는다.

- 채점은 팀원의 run_raw_eval.py를 그대로 불러다 쓴다 ((행위, 슬롯, 값) 집합이 완전히 같아야 맞음).
  여기서 새로 짠 부분은 "모델에게 묻기" 하나뿐이다 (원본은 vLLM 서버에 HTTP로 묻고, 여기서는 GPU의 모델에 직접 묻는다).
- 모델을 한 번 올려 먼저 학습 전 상태로 풀고, 이어서 LoRA 어댑터를 얹어 같은 문제를 다시 푼다.
- 실행:  python run_raw_eval_local.py --kit 평가폴더 --adapter 어댑터폴더 --out_dir 결과폴더
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
    p.add_argument("--kit", required=True, help="run_raw_eval.py와 eval_raw_elderly.jsonl이 있는 폴더")
    p.add_argument("--out_dir", required=True, help="결과 jsonl을 둘 폴더")
    p.add_argument("--model", default="Qwen/Qwen3.8-27B")
    p.add_argument("--adapter", default=None, help="LoRA 어댑터 폴더. 없으면 학습 전만 잰다")
    p.add_argument("--name", default="after", help="학습 후 결과 파일 이름 (results_raw_<name>.jsonl)")
    p.add_argument("--skip_base", action="store_true", help="학습 전 풀이를 건너뛴다 (이미 결과가 있을 때)")
    p.add_argument("--max_new_tokens", type=int, default=200)   # 원본 max_tokens와 같게
    p.add_argument("--limit", type=int, default=0, help="앞에서 N문제만 (시험 실행용)")
    return p.parse_args()


def load_kit(kit):
    """원본 노인 평가 스크립트를 모듈로 불러온다. 파일은 고치지 않고, __pycache__도 만들지 않는다."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(kit).resolve()))
    import run_raw_eval
    return run_raw_eval


def ask(model, tok, messages, a):
    """원본에서 HTTP 요청 부분만 GPU 생성으로 바꾼 것. 원본처럼 temperature 0, 비추론 모드."""
    prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                     enable_thinking=False)
    ids = tok(prompt, return_tensors="pt").to(0)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=a.max_new_tokens, do_sample=False)
    return tok.decode(out[0, ids["input_ids"].shape[1]:], skip_special_tokens=True)


def solve(model, tok, rows, a, label, out):
    """70건을 풀어 원본과 같은 형식(입력 행 + raw)으로 저장한다."""
    t0 = time.time()
    with open(out, "w", encoding="utf-8") as f:
        for i, r in enumerate(rows, 1):
            try:
                raw = ask(model, tok, r["messages"][:2], a)   # system + user만 주고, 정답(assistant)은 채점용
            except Exception as e:  # noqa  원본처럼 실패도 한 행으로 남긴다
                raw = "ERROR " + str(e)
            f.write(json.dumps({**r, "raw": raw}, ensure_ascii=False) + "\n")
            if i % 10 == 0:
                print(f"[gen] {label} {i}/{len(rows)}  {time.time()-t0:.0f}s 경과", flush=True)
    print(f"[{label}] 끝: {time.time()-t0:.0f}s -> {out}", flush=True)
    return str(out)


def main():
    a = parse_args()
    kit = load_kit(a.kit)
    with open(Path(a.kit) / "eval_raw_elderly.jsonl", encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    if a.limit:
        rows = rows[:a.limit]
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[data] {len(rows)}문제 (adapter {a.adapter or '없음'})", flush=True)

    # 학습과 같은 4bit(NF4) 설정으로 모델을 GPU 0번에 올린다.
    tok = AutoTokenizer.from_pretrained(a.model)
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(a.model, quantization_config=bnb,
                                                 device_map={"": 0}, dtype=torch.bfloat16)
    model.eval()

    base_out = out_dir / "results_raw_base.jsonl"
    files = [str(base_out) if a.skip_base else solve(model, tok, rows, a, "학습 전", base_out)]
    if a.adapter:   # 같은 4bit 원본 위에 LoRA 어댑터를 얹어 다시 푼다
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, a.adapter)
        model.eval()
        files.append(solve(model, tok, rows, a, "학습 후", out_dir / f"results_raw_{a.name}.jsonl"))

    kit.score(files)   # 원본 채점: 전체(턴 전체 일치) · 슬롯별 · 패턴별 + 개선/악화 사례
    print("\n[done]", flush=True)


if __name__ == "__main__":
    main()
