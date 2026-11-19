"""farm7 vLLM 서버에 백엔드와 같은 요청을 보내 분류기 한 턴의 지연 시간과 처리량을 잰다.

용도: 최종 발표(12/11)용 지연 시간 측정. 같은 vLLM · 같은 GPU에서 27B와 14B(또는 어댑터)의
      한 턴 지연 시간(p50/p95)과 처리량을 동시 요청 1 · 8에서 비교한다.

- 요청 내용: 학습 검증셋(sft_valid_v3_1.jsonl)의 system + user 메시지. 백엔드 classifier.py가 보내는 형식과 같다.
- 요청 설정: classifier.py의 call_vllm과 같다 (temperature 0, max_tokens 300, JSON schema 강제, 비추론 모드).
- 측정: 동시 요청 수마다 워밍업 요청을 먼저 보내 버리고, 본 요청을 3번 반복해 잰다.
  지연 시간 = 요청을 보내고 응답 전체를 받을 때까지의 시간. p50/p95와 처리량(요청/초, 출력 토큰/초)을 낸다.
- 실행:  python latency_vllm.py --model Qwen3.8-27B --tag 27b-base
- 결과: runs/latency/<태그>/summary.json, requests.jsonl (요청 하나마다 한 줄)
"""
import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]          # ~/capstone_design_2
REPO = Path(__file__).resolve().parents[2]          # 레포 루트
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / "backend"))
from classifier import OUTPUT_SCHEMA                 # 백엔드가 쓰는 출력 형식을 그대로 쓴다


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, help="vLLM의 모델 이름 (기본 모델 또는 LoRA 이름)")
    p.add_argument("--tag", required=True, help="결과 폴더 이름. 예: 27b-base")
    p.add_argument("--base_url", default="http://localhost:8001/v1")
    p.add_argument("--data", default=str(ROOT / "data/v31_trainset/sft_valid_v3_1.jsonl"))
    p.add_argument("--concurrency", type=int, nargs="+", default=[1, 8])
    p.add_argument("--requests", type=int, default=100, help="반복 1번에 보내는 본 요청 수")
    p.add_argument("--reps", type=int, default=3)
    p.add_argument("--warmup", type=int, default=8, help="동시 요청 수마다 먼저 보내고 버리는 요청 수")
    p.add_argument("--gpus", default="0,2", help="메모리를 기록할 GPU 번호 (vLLM이 쓰는 GPU)")
    return p.parse_args()


def ask(messages, a):
    """요청 하나를 보내고 (지연 시간 초, 출력 토큰 수, 오류)를 돌려준다."""
    payload = {"model": a.model, "messages": messages, "temperature": 0, "max_tokens": 300,
               "response_format": {"type": "json_schema",
                                   "json_schema": {"name": "nlu_output", "schema": OUTPUT_SCHEMA}},
               "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(a.base_url.rstrip("/") + "/chat/completions", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read())
        return time.perf_counter() - t0, body["usage"]["completion_tokens"], None
    except Exception as e:
        return time.perf_counter() - t0, 0, str(e)


def run_batch(prompts, conc, a):
    """prompts를 동시에 conc개씩 보내고 (요청별 결과, 전체 걸린 시간)을 돌려준다."""
    t0 = time.perf_counter()
    with ThreadPoolExecutor(conc) as ex:
        results = list(ex.map(lambda m: ask(m, a), prompts))
    return results, time.perf_counter() - t0


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(q / 100 * (len(xs) - 1)))]


def gpu_mem(gpus):
    out = subprocess.run(["nvidia-smi", f"--id={gpus}", "--query-gpu=index,memory.used,memory.total",
                          "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
    return [dict(zip(["gpu", "used_mib", "total_mib"], map(int, l.split(",")))) for l in out.strip().splitlines()]


def main():
    a = parse_args()
    with open(a.data, encoding="utf-8") as f:
        prompts = [json.loads(l)["messages"][:2] for l in f]
    out_dir = ROOT / "runs/latency" / a.tag
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[data] {len(prompts)}개 입력, model {a.model}, 동시 {a.concurrency}, 반복 {a.reps}×{a.requests}요청", flush=True)

    summary = {"model": a.model, "tag": a.tag, "started": time.strftime("%F %T"), "gpu_mem_before": gpu_mem(a.gpus),
               "settings": {k: v for k, v in vars(a).items() if k not in ("tag",)}, "results": []}
    with open(out_dir / "requests.jsonl", "w", encoding="utf-8") as log:
        for conc in a.concurrency:
            run_batch(prompts[:a.warmup], conc, a)          # 워밍업: 결과를 버린다
            for rep in range(1, a.reps + 1):
                # 반복마다 다른 입력을 쓴다 (입력 목록을 돌아가며 사용)
                start = ((rep - 1) * a.requests) % len(prompts)
                batch = [prompts[(start + i) % len(prompts)] for i in range(a.requests)]
                res, wall = run_batch(batch, conc, a)
                ok = [(lat, tok) for lat, tok, err in res if err is None]
                lats = [lat for lat, _ in ok]
                row = {"concurrency": conc, "rep": rep, "n": len(res), "errors": len(res) - len(ok),
                       "p50_s": round(pct(lats, 50), 3), "p95_s": round(pct(lats, 95), 3),
                       "mean_s": round(statistics.mean(lats), 3),
                       "req_per_s": round(len(ok) / wall, 2),
                       "out_tok_per_s": round(sum(t for _, t in ok) / wall, 1),
                       "mean_out_tok": round(statistics.mean(t for _, t in ok), 1), "wall_s": round(wall, 1)}
                summary["results"].append(row)
                print(f"[conc {conc} rep {rep}] p50 {row['p50_s']}s p95 {row['p95_s']}s "
                      f"{row['req_per_s']} req/s {row['out_tok_per_s']} tok/s 오류 {row['errors']}", flush=True)
                for (lat, tok, err) in res:
                    log.write(json.dumps({"concurrency": conc, "rep": rep, "latency_s": round(lat, 4),
                                          "out_tokens": tok, "error": err}, ensure_ascii=False) + "\n")

    # 동시 요청 수마다 3번 반복의 평균과 범위(최소~최대)
    agg = {}
    for conc in a.concurrency:
        rows = [r for r in summary["results"] if r["concurrency"] == conc]
        agg[conc] = {k: {"mean": round(statistics.mean(r[k] for r in rows), 3),
                         "min": min(r[k] for r in rows), "max": max(r[k] for r in rows)}
                     for k in ("p50_s", "p95_s", "req_per_s", "out_tok_per_s")}
    summary["aggregate"] = agg
    summary["gpu_mem_after"] = gpu_mem(a.gpus)
    summary["finished"] = time.strftime("%F %T")
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(agg, indent=2), flush=True)
    print(f"[done] -> {out_dir}", flush=True)


if __name__ == "__main__":
    main()
