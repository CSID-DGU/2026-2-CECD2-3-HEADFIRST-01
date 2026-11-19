"""노인 raw test 62를 farm7 vLLM 서버에 물어서 풀고 팀원의 evaluate_raw.py로 채점한다.

용도: 학교 서버 GPU 대신 vLLM 서버로 평가하게 된 뒤(2026-10-28 이후) raw test 62를 잰다.
      최종 발표용 학습 전 · A′ v3.1 비교에 쓴다. eval_all_vllm.sh가 이 스크립트를 부른다.

- run_raw_test_local.py와 문제 · 결과 형식 · 채점이 같다. 다른 점은 "모델에게 묻기"를 GPU 직접 대신 vLLM HTTP로 한다는 것뿐이다.
- 학습 전: --model Qwen3.8-27B / 학습 후: --model 어댑터이름 (serve_vllm.sh의 --lora-modules에 등록한 이름)
- 실행:  python run_raw_test_vllm.py --kit raw_elderly_v1폴더 --out 결과.jsonl --model Qwen3.8-27B
- 표준 라이브러리만 쓴다.
"""
import argparse
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True, help="evaluate_raw.py와 raw_노인_test.jsonl이 있는 폴더")
    p.add_argument("--data", default="raw_노인_test.jsonl")
    p.add_argument("--out", required=True, help="결과 jsonl (evaluate_raw.py 형식)")
    p.add_argument("--base_url", default="http://localhost:8001/v1")
    p.add_argument("--model", required=True, help="vLLM의 모델 이름 (기본 모델 또는 LoRA 이름)")
    p.add_argument("--max_new_tokens", type=int, default=200)   # run_raw_test_local.py와 같게
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--limit", type=int, default=0, help="앞에서 N문제만 (시험 실행용)")
    return p.parse_args()


def load_kit(kit):
    """팀원의 채점 스크립트를 모듈로 불러온다. 파일은 고치지 않고, __pycache__도 만들지 않는다."""
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(Path(kit).resolve()))
    import evaluate_raw
    return evaluate_raw


def ask(messages, a):
    """temperature 0(가장 그럴듯한 답 하나), 비추론 모드. 학습 때와 같은 대화 형식이다."""
    payload = {"model": a.model, "messages": messages, "temperature": 0, "max_tokens": a.max_new_tokens,
               "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(a.base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())["choices"][0]["message"]["content"]


def solve_one(r, a):
    """한 문제를 풀어 evaluate_raw.py 형식의 줄로 만든다. JSON으로 못 읽은 답(파싱 실패)은 pred를 빈 문자열로 둔다."""
    try:
        raw = ask(r["messages"][:2], a)
    except Exception as e:
        raw = f"ERROR: {e}"
    try:
        pred = json.dumps(json.loads(raw), ensure_ascii=False)
    except Exception:
        pred = ""
    return {"dialogue_id": r["dialogue_id"], "pattern": r.get("pattern", ""),
            "category": ["노인"], "utterance": r["messages"][1]["content"].split("[마지막 USER 발화]")[-1].strip(),
            "gold": r["messages"][2]["content"], "pred": pred, "raw": raw}


def main():
    a = parse_args()
    kit = load_kit(a.kit)
    with open(Path(a.kit) / a.data, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    if a.limit:
        rows = rows[:a.limit]
    print(f"[data] {a.data} {len(rows)}문제, model {a.model}", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:   # map은 입력 순서를 지킨다
        outs = list(ex.map(lambda r: solve_one(r, a), rows))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for o in outs:
            f.write(json.dumps(o, ensure_ascii=False) + "\n")
    fails = sum(1 for o in outs if not o["pred"])
    errors = sum(1 for o in outs if o["raw"].startswith("ERROR:"))
    print(f"[gen] {time.time()-t0:.0f}s, 파싱 실패 {fails} (요청 오류 {errors}) -> {out}", flush=True)

    # 원본 채점: JGA · slot F1 · act별 P/R/F1 · macro-F1 · 셀별 + 다수결 베이스라인
    kit.cmd_score(argparse.Namespace(pred=str(out), track="노인"))
    print("\n[done]", flush=True)


if __name__ == "__main__":
    main()
