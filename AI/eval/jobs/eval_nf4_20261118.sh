#!/bin/bash
# 2026-11-18: 하드 테스트셋(dev·test)을 transformers + nf4로 평가한다 (학습 전 27B, A′). GPU 3장을 쓰려고 vLLM을 잠시 끈다.
#   0) transformers 가상환경(setup_local_venv.sh) 설치가 끝날 때까지 기다린다 (vLLM은 그동안 켜져 있다)
#   1) vLLM 끄기 → 2) GPU 3장에서 하드 테스트셋 3등분 풀이 → 합치기 → 채점
#   3) A′ 실발화 227 (nf4 예측 파일이 없어서) → 4) vLLM 다시 켜기 (실패해도 항상 켠다)
# 실행: setsid nohup bash eval_nf4_20261118.sh > ~/capstone_design_2/runs/logs/eval_nf4_20261118.log 2>&1 &
set -uo pipefail
R=~/capstone_design_2
REPO=$R/2026-2-CECD2-3-HEADFIRST-01
K=$R/hardset_eval_handoff_20261118
O=$R/runs/eval_nf4
AP=$R/runs/from_backup_1022/v31-r16-e3/checkpoint-842   # 원래 A′ (키 이름을 바꾸지 않은 원본, PeftModel용)
VENV=/var/tmp/csuhyeon/venvs/qwen
export PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 OMP_NUM_THREADS=8
kst() { TZ=Asia/Seoul date '+%F %T KST'; }
mkdir -p $O/hard $O/real227_Aprime

restart_vllm() {
  echo "== [4] vLLM 다시 켜기 $(kst)"
  bash /var/tmp/csuhyeon/vllm_ctl.sh start
  for i in $(seq 120); do curl -sf -m5 localhost:8001/v1/models | grep -q '"id":"Aprime"' && break; sleep 5; done
  echo "vLLM: $(bash /var/tmp/csuhyeon/vllm_ctl.sh status | head -1) $(kst)"
}

echo "== [0] 가상환경 설치 기다리기 $(kst)"
for i in $(seq 360); do grep -q "== ALL DONE" $R/runs/logs/setup_qwen_venv_20261118.log && break; sleep 10; done
grep -q "== ALL DONE" $R/runs/logs/setup_qwen_venv_20261118.log || { echo "!! 가상환경 설치가 1시간 안에 끝나지 않음. vLLM은 끄지 않았음"; exit 1; }
tail -15 $R/runs/logs/setup_qwen_venv_20261118.log
source $VENV/bin/activate

echo "== [1] vLLM 끄기 $(kst)"
trap restart_vllm EXIT          # 여기부터는 실패해도 끝날 때 vLLM을 다시 켠다
bash /var/tmp/csuhyeon/vllm_ctl.sh stop
for i in $(seq 60); do pgrep -f "^/var/tmp/csuhyeon/venvs/vllm/bin/python .*vllm serve" >/dev/null || break; sleep 5; done
sleep 10; nvidia-smi --query-gpu=index,memory.used --format=csv,noheader

echo "== [2] 하드 테스트셋 (GPU 0·1·2, 3등분) $(kst)"
for g in 0 1 2; do
  CUDA_VISIBLE_DEVICES=$g python $REPO/AI/eval/run_hardset_local.py --kit $K --out_dir $O/hard \
    --adapter Aprime=$AP --shard $g --nshards 3 > $O/hard/shard_$g.log 2>&1 &
done
wait
tail -2 $O/hard/shard_*.log
python $REPO/AI/eval/run_hardset_local.py --kit $K --out_dir $O/hard --adapter Aprime=$AP --nshards 3 --merge || exit 1
for s in dev test; do
  for n in untrained Aprime; do python3 -B $K/score_hard.py score --pred $O/hard/pred_${s}_$n.jsonl > $O/hard/score_${s}_$n.txt 2>&1; done
  python3 -B $K/score_hard.py compare --base $O/hard/pred_${s}_untrained.jsonl --model $O/hard/pred_${s}_Aprime.jsonl > $O/hard/compare_${s}.txt 2>&1
  sed -n 1,7p $O/hard/score_${s}_untrained.txt; sed -n 1,7p $O/hard/score_${s}_Aprime.txt
done

echo "== [3] A′ 실발화 227 (GPU 3장) $(kst)"
cd $REPO
CUDA_VISIBLE_DEVICES=0,1,2 accelerate launch --num_processes 3 AI/eval/run_track1_local.py --kit $R/data/eval_real \
  --script run_track1_v01 --data testset_v0_1.jsonl --out_dir $O/real227_Aprime --adapter $AP --modes base \
  > $O/real227_Aprime/run.log 2>&1
tail -10 $O/real227_Aprime/run.log

echo "== ALL DONE $(kst)"
