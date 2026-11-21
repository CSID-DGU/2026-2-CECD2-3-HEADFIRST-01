#!/bin/bash
# 2026-11-21: 27B에 v3.2 어댑터(v32A · v32B)를 붙인 상태의 응답 속도를 잰다. 14B 어댑터(q14A · q14B)와 같은 조건으로 비교하기 위해서다.
#   vLLM은 끄지 않는다 (v32A · v32B는 27B vLLM에 이미 올라와 있다). 측정 중에는 백엔드 응답이 느려진다.
#   1) seed 평가(eval_seeds_20261120.sh)가 GPU를 쓰는 동안 기다린다 → 2) v32A · v32B가 올라와 있는지 확인
#   3) 어댑터마다 latency_vllm.py (약 16분씩) → runs/latency/27b-v32A, runs/latency/27b-v32B
# 실행: setsid nohup bash latency_27b_adapters_20261121.sh > ~/capstone_design_2/runs/logs/latency-27b-adapters.log 2>&1 < /dev/null &
set -uo pipefail
R=~/capstone_design_2
E=${E:-$R/deploy/app/AI/eval}   # 저장소가 develop으로 바뀌어 AI/eval이 없다. deploy 사본 = feat/eval-scripts와 같은 파일, OUTPUT_SCHEMA도 같음
PY=$R/2026-2-CECD2-3-HEADFIRST-01/backend/.venv/bin/python
URL=http://localhost:8001
export PYTHONDONTWRITEBYTECODE=1
kst() { TZ=Asia/Seoul date '+%F %T KST'; }
has_model() { curl -sf -m5 $URL/v1/models | grep -q "\"id\":\"$1\""; }

echo "== [1] seed 평가가 끝나기를 기다린다 $(kst)"
while pgrep -f "eval_seeds_20261120.sh" > /dev/null; do sleep 30; done
echo "seed 평가 끝 $(kst)"
tail -3 $R/runs/logs/eval_seeds_20261120.log

echo "== [2] 어댑터 확인 $(kst)"
for n in v32A v32B; do has_model $n || { echo "!! $n 이 27B vLLM에 없다"; exit 1; }; done
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader

for n in v32A v32B; do
  echo "== [3] 응답 속도 $n $(kst)"
  # deploy 사본은 자기 위치(deploy/) 기준으로 data·runs를 찾으므로 데이터를 직접 주고, 결과를 runs/latency로 옮긴다
  $PY $E/latency_vllm.py --model $n --tag 27b-$n --data $R/data/v31_trainset/sft_valid_v3_1.jsonl \
    > $R/runs/logs/latency-27b-$n.log 2>&1 || { echo "!! $n 측정 실패"; tail -20 $R/runs/logs/latency-27b-$n.log; exit 1; }
  out=$(dirname $(dirname $E))/../runs/latency/27b-$n
  [ "$(realpath $out)" != "$(realpath -m $R/runs/latency/27b-$n)" ] && mv $out $R/runs/latency/27b-$n
  grep -E "^\[conc" $R/runs/logs/latency-27b-$n.log
done
echo "== ALL DONE $(kst)"
