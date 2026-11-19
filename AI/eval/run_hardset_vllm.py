"""하드 테스트셋(dev 100 / test 200)을 farm7 vLLM 서버에 물어서 풀고, 팀원의 score_hard.py가 읽는 예측 파일을 만든다.

용도: 최종 발표용 하드 테스트셋 평가. 팀원이 2026-11-18에 넘긴 hardset_eval_handoff_20261118로
      학습 전 모델과 어댑터(예: A′ v3.1)의 예측 파일을 만들어 팀원의 score_hard.py로 채점받는다.

- 입력은 hardset_eval_handoff_20261118의 *_sft.jsonl(system + user)이다. assistant(정답)는 보내지 않는다.
- 결과는 *_eval_turns.jsonl 각 줄에 "pred"(모델 출력 문자열)와 "raw"를 붙인 jsonl이다 (README가 요청한 형식).
- 요청 설정은 run_raw_test_vllm.py와 같다: temperature 0, 비추론 모드. max_tokens는 생성 620 채점(check_responses.py)과 같은 1024.
- 실행:  python run_hardset_vllm.py --kit hardset_eval_handoff_20261118폴더 --split dev --model Qwen3.8-27B --out pred_dev_untrained.jsonl
- 표준 라이브러리만 쓴다.
"""
import argparse
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

FILES = {"dev": ("hard_dev_sft.jsonl", "hard_dev_eval_turns.jsonl"),
         "test": ("test/hard_test_sft.jsonl", "test/hard_test_eval_turns.jsonl")}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--kit", required=True, help="hardset_eval_handoff_20261118 폴더")
    p.add_argument("--split", required=True, choices=list(FILES))
    p.add_argument("--out", required=True, help="예측 jsonl (eval_turns + pred)")
    p.add_argument("--base_url", default="http://localhost:8001/v1")
    p.add_argument("--model", required=True, help="vLLM의 모델 이름 (기본 모델 또는 LoRA 이름)")
    p.add_argument("--max_new_tokens", type=int, default=1024)
    p.add_argument("--workers", type=int, default=8)
    return p.parse_args()


def ask(messages, a):
    """temperature 0, 비추론 모드. 학습 때와 같은 대화 형식이다."""
    payload = {"model": a.model, "messages": messages, "temperature": 0, "max_tokens": a.max_new_tokens,
               "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(a.base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"


def main():
    a = parse_args()
    kit = Path(a.kit)
    sft_name, turns_name = FILES[a.split]
    sft = [json.loads(l) for l in (kit / sft_name).open(encoding="utf-8") if l.strip()]
    turns = [json.loads(l) for l in (kit / turns_name).open(encoding="utf-8") if l.strip()]
    # 두 파일은 같은 순서로 같은 문제를 담고 있어야 한다
    assert len(sft) == len(turns) and all(s["dialogue_id"] == t["dialogue_id"] for s, t in zip(sft, turns))
    print(f"[data] {a.split} {len(turns)}문제, model {a.model}", flush=True)

    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:   # map은 입력 순서를 지킨다
        raws = list(ex.map(lambda s: ask(s["messages"][:2], a), sft))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fails = errors = 0
    with open(out, "w", encoding="utf-8") as f:
        for t, raw in zip(turns, raws):
            errors += raw.startswith("ERROR:")
            try:
                json.loads(raw)
            except Exception:
                fails += 1
            f.write(json.dumps({**t, "pred": raw, "raw": raw, "model": a.model}, ensure_ascii=False) + "\n")
    print(f"[gen] {time.time()-t0:.0f}s, 파싱 실패 {fails} (요청 오류 {errors}) -> {out}", flush=True)


if __name__ == "__main__":
    main()
