#!/bin/bash
# 2026-11-18: 원래 A′(backup_1022.tar의 v31-r16-e3/checkpoint-842)를 vLLM에 올리고 평가한다.
#   1) 키 이름 변환  2) vLLM 재시작(약 5~6분, 그동안 백엔드 시연 멈춤)
#   3) 확인: 학습 전 27B의 raw 테스트 62 답이 재시작 전과 같은지, A′ 답이 학습 전 27B와 다른지(어댑터 적용)
#   4) A′ 평가: 하드 테스트셋 dev·test (+ score_hard.py score/compare), raw 테스트 62 · 실발화 227 · 생성 620
# 실행: setsid nohup bash eval_aprime_20261118.sh > ~/capstone_design_2/runs/logs/eval_aprime_20261118.log 2>&1 &
set -uo pipefail
R=~/capstone_design_2
E=$R/2026-2-CECD2-3-HEADFIRST-01/AI/eval
PY=$R/2026-2-CECD2-3-HEADFIRST-01/backend/.venv/bin/python
K=$R/hardset_eval_handoff_20261118
B=$R/runs/eval_vllm/base
O=$R/runs/eval_vllm/Aprime
URL=http://localhost:8001/v1
export PYTHONDONTWRITEBYTECODE=1
kst() { TZ=Asia/Seoul date '+%F %T KST'; }
mkdir -p $O/hard $B/after_restart

echo "== [1] 키 이름 변환 $(kst)"
if [ ! -d ~/var_tmp_backup_20261107/adapters/v31-ckpt842-vl ]; then
  bash $R/envs/vllm/add_adapter.sh $R/runs/from_backup_1022/v31-r16-e3/checkpoint-842 v31-ckpt842 || exit 1
fi

echo "== [2] vLLM 재시작 $(kst)"
bash /var/tmp/csuhyeon/vllm_ctl.sh stop
for i in $(seq 60); do pgrep -f "^/var/tmp/csuhyeon/venvs/vllm/bin/python .*vllm serve" >/dev/null || break; sleep 5; done
sleep 10
bash /var/tmp/csuhyeon/vllm_ctl.sh start
for i in $(seq 120); do   # 최대 10분
  curl -sf -m5 $URL/models | grep -q '"id":"Aprime"' && break; sleep 5
done
curl -sf -m5 $URL/models | grep -q '"id":"Aprime"' || { echo "!! 10분 안에 vLLM이 준비되지 않음. 평가 안 함"; tail -20 /var/tmp/csuhyeon/serve_vllm.log; exit 1; }
echo "준비됨 $(kst): $(bash /var/tmp/csuhyeon/vllm_ctl.sh status | head -1)"

echo "== [3] 확인 $(kst)"
$PY $E/run_raw_test_vllm.py --kit $R/data/raw_elderly_v1 --model Qwen3.8-27B --out $B/after_restart/raw62.jsonl > $B/after_restart/raw62.log 2>&1
$PY $E/run_raw_test_vllm.py --kit $R/data/raw_elderly_v1 --model Aprime --out $O/raw62_check.jsonl > $O/raw62_check.log 2>&1
python3 - "$B/raw62.jsonl" "$B/after_restart/raw62.jsonl" "$O/raw62_check.jsonl" <<'PY' || exit 1
import json, sys
a, b, c = ([json.loads(l)["raw"] for l in open(p)] for p in sys.argv[1:])
same_base = sum(x == y for x, y in zip(a, b)); diff_ap = sum(x != z for x, z in zip(a, c))
print(f"학습 전 27B 재시작 전후 같은 답: {same_base}/{len(a)}")
print(f"A′ 답이 학습 전 27B와 다른 문항: {diff_ap}/{len(a)}")
if diff_ap == 0:
    sys.exit("!! A′ 답이 학습 전 27B와 모두 같음 → 어댑터가 적용되지 않음. 평가 중단")
PY

echo "== [4-1] 하드 테스트셋 $(kst)"
for s in dev test; do
  $PY $E/run_hardset_vllm.py --kit $K --split $s --model Aprime --out $O/hard/pred_${s}_Aprime.jsonl
  python3 -B $K/score_hard.py score --pred $O/hard/pred_${s}_Aprime.jsonl > $O/hard/score_${s}_Aprime.txt 2>&1
  python3 -B $K/score_hard.py compare --base $B/hard/pred_${s}_untrained.jsonl --model $O/hard/pred_${s}_Aprime.jsonl \
    > $O/hard/compare_${s}.txt 2>&1
done
sed -n 1,7p $O/hard/score_dev_Aprime.txt; sed -n 1,7p $O/hard/score_test_Aprime.txt

echo "== [4-2] raw 테스트 62 · 실발화 227 · 생성 620 $(kst)"
bash $E/eval_all_vllm.sh Aprime Aprime

echo "== ALL DONE $(kst)"
