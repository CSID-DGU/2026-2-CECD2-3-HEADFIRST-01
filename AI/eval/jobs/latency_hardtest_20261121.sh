#!/bin/bash
# 2026-11-21: 응답 속도를 하드 test 200문제로 다시 잰다 (계획서 작업 5: "시험지 전체를 3회 반복").
#   입력 = hardset_eval_handoff_20261118/test/hard_test_sft.jsonl의 system + user 메시지 200개. 동시 요청 1 · 8, 반복마다 200개 전체, 3회.
#   1) 27B vLLM(지금 켜진 것)에서 v32A · v32B → 2) 27B 끄고(백엔드 멈춤) 14B + q14A · q14B 켜기
#   3) q14A · q14B → 4) 14B 끄고 27B 다시 켜기(실패해도 항상)
#   결과: runs/latency/<27b|14b>-<이름>-hard200/ (test 예측 내용은 남기지 않는다: latency_vllm.py는 시간과 토큰 수만 적는다)
# 실행: setsid nohup bash latency_hardtest_20261121.sh > ~/capstone_design_2/runs/logs/latency-hardtest-20261121.log 2>&1 < /dev/null &
set -uo pipefail
R=~/capstone_design_2
E=${E:-$R/deploy/app/AI/eval}   # 저장소가 develop이라 AI/eval이 없다. deploy 사본 = feat/eval-scripts와 같은 파일
PY=$R/2026-2-CECD2-3-HEADFIRST-01/backend/.venv/bin/python
DATA=$R/hardset_eval_handoff_20261118/test/hard_test_sft.jsonl
AD=$HOME/var_tmp_backup_20261107/adapters
URL=http://localhost:8001
LOG14=/var/tmp/csuhyeon/serve_vllm_14b.log
export PYTHONDONTWRITEBYTECODE=1
kst() { TZ=Asia/Seoul date '+%F %T KST'; }
has_model() { curl -sf -m5 $URL/v1/models | grep -q "\"id\":\"$1\""; }
vpid() { pgrep -f "^/var/tmp/csuhyeon/venvs/vllm/bin/python .*vllm serve" | head -1; }
wait_down() { for i in $(seq 60); do [ -z "$(vpid)" ] && break; sleep 5; done; sleep 10; }

lat() {   # lat <vLLM 이름> <태그>
  echo "== 응답 속도 $1 $(kst)"
  $PY $E/latency_vllm.py --model $1 --tag $2 --data $DATA --requests 200 \
    > $R/runs/logs/latency-$2.log 2>&1 || { echo "!! $1 측정 실패"; tail -20 $R/runs/logs/latency-$2.log; exit 1; }
  # deploy 사본은 deploy/runs/latency에 쓴다 → runs/latency로 옮긴다
  src=$(realpath -m $E/../../../runs/latency/$2)
  [ "$src" != "$(realpath -m $R/runs/latency/$2)" ] && { rm -rf $R/runs/latency/$2; mv $src $R/runs/latency/$2; }
  grep -E "^\[conc" $R/runs/logs/latency-$2.log
}

restart_27b() {
  echo "== [4] 14B 끄고 27B vLLM 다시 켜기 $(kst)"
  p=$(vpid); [ -n "$p" ] && kill "$p"; wait_down
  bash /var/tmp/csuhyeon/vllm_ctl.sh start
  for i in $(seq 120); do has_model Aprime && break; sleep 5; done
  echo "27B: $(bash /var/tmp/csuhyeon/vllm_ctl.sh status | head -1) $(kst)"
  rmdir $R/deploy/runs/latency $R/deploy/runs 2>/dev/null
}

echo "== [1] 27B $(kst)"
for n in v32A v32B; do has_model $n || { echo "!! $n 이 27B vLLM에 없다"; exit 1; }; done
for n in v32A v32B; do lat $n 27b-$n-hard200; done

echo "== [2] 27B vLLM 끄기 (백엔드 멈춤) → 14B 켜기 $(kst)"
trap restart_27b EXIT
bash /var/tmp/csuhyeon/vllm_ctl.sh stop; wait_down
nohup bash $R/envs/vllm/serve_vllm_14b.sh --lora-modules q14B=$AD/q14B-ckpt1150-vl q14A=$AD/q14A-ckpt1152-vl > $LOG14 2>&1 &
for i in $(seq 180); do
  has_model q14A && break
  [ -z "$(vpid)" ] && [ $i -gt 6 ] && break
  sleep 5
done
for n in q14A q14B; do has_model $n || { echo "!! $n 이 준비되지 않음"; tail -30 $LOG14; exit 1; }; done
echo "14B 준비됨 $(kst)"
grep -hE "Model loading took|Available KV cache memory|GPU KV cache size" $LOG14 | sed -E 's/^.*\] //'

echo "== [3] 14B $(kst)"
for n in q14A q14B; do lat $n 14b-$n-hard200; done
echo "== ALL DONE (27B 다시 켜기 전) $(kst)"
