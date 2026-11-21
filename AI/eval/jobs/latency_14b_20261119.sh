#!/bin/bash
# 2026-11-19: 14B 응답 속도 측정. 27B vLLM을 끄고(백엔드 멈춤) 같은 GPU·같은 설정으로 14B를 띄워 latency_vllm.py로 잰다.
#   1) 27B vLLM 끄기 → 2) 14B 켜기 → 3) 요청 1개로 확인 → 4) 측정(runs/latency/14b-base) → 5) 14B 끄고 27B 다시 켜기(실패해도 항상)
# 실행: setsid nohup bash latency_14b_20261119.sh > ~/capstone_design_2/runs/logs/latency-14b-base.log 2>&1 &
set -uo pipefail
R=~/capstone_design_2
E=$R/2026-2-CECD2-3-HEADFIRST-01/AI/eval
PY=$R/2026-2-CECD2-3-HEADFIRST-01/backend/.venv/bin/python
URL=http://localhost:8001/v1
LOG14=/var/tmp/csuhyeon/serve_vllm_14b.log
export PYTHONDONTWRITEBYTECODE=1
kst() { TZ=Asia/Seoul date '+%F %T KST'; }
vpid() { pgrep -f "^/var/tmp/csuhyeon/venvs/vllm/bin/python .*vllm serve" | head -1; }
wait_down() { for i in $(seq 60); do [ -z "$(vpid)" ] && break; sleep 5; done; sleep 10; }

restart_27b() {
  echo "== [5] 14B 끄고 27B 다시 켜기 $(kst)"
  p=$(vpid); [ -n "$p" ] && kill "$p"; wait_down
  bash /var/tmp/csuhyeon/vllm_ctl.sh start
  for i in $(seq 120); do curl -sf -m5 $URL/models | grep -q '"id":"Aprime"' && break; sleep 5; done
  echo "27B: $(bash /var/tmp/csuhyeon/vllm_ctl.sh status | head -1) $(kst)"
}

echo "== [1] 27B vLLM 끄기 $(kst)"
trap restart_27b EXIT
bash /var/tmp/csuhyeon/vllm_ctl.sh stop; wait_down
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader

echo "== [2] 14B 켜기 $(kst)"
nohup bash $R/envs/vllm/serve_vllm_14b.sh > $LOG14 2>&1 &
for i in $(seq 180); do   # 최대 15분
  curl -sf -m5 $URL/models | grep -q '"id":"Qwen3-14B"' && break
  [ -z "$(vpid)" ] && [ $i -gt 6 ] && break   # 서버가 죽었으면 기다리지 않는다
  sleep 5
done
curl -sf -m5 $URL/models | grep -q '"id":"Qwen3-14B"' || { echo "!! 14B가 준비되지 않음"; tail -30 $LOG14; exit 1; }
echo "14B 준비됨 $(kst)"

echo "== [3] 요청 1개로 확인 $(kst)"
curl -s -m60 $URL/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"Qwen3-14B","messages":[{"role":"user","content":"안녕하세요"}],"max_tokens":20,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["choices"][0]["message"]["content"])' || exit 1

echo "== [4] 측정 $(kst)"
$PY $E/latency_vllm.py --model Qwen3-14B --tag 14b-base || exit 1

echo "== ALL DONE (27B 다시 켜기 전) $(kst)"
