#!/bin/bash
# v3.2 실험 A · B를 A′와 같은 조건으로 학습한다 (H200 GPU 0번 1장).
#   같은 조건: train_qlora.py 기본값(4bit QLoRA, r 16, alpha 32, lr 2e-4, max_len 1024, 3에폭, seed 42),
#             실효 배치 12(--batch 4 --grad_accum 3, farm7 A′의 1×4×GPU 3장과 같음), 검증 sft_valid_v3_1.jsonl
#   바뀐 것: 학습 데이터만 (sft_train_v3_2_A.jsonl / sft_train_v3_2_B.jsonl)
# 실행 (tmux 안에서):  bash ~/dgustu/code/AI/train/run_v32.sh A B     ← A 다음 B. 하나만이면 A 또는 B
# 결과: ~/dgustu/runs/v32A-r16-e3/checkpoint-{576,1152,1728}, ~/dgustu/runs/v32B-r16-e3/checkpoint-{575,1150,1725}
#       에폭 2 체크포인트(A 1152, B 1150)를 farm7로 가져간다 → pack_v32.sh
# 로그: ~/dgustu/logs/v32A-r16-e3.log, v32B-r16-e3.log
set -uo pipefail
D=$HOME/dgustu
source $D/envs/qwen/bin/activate
cd $D/code
export CUDA_VISIBLE_DEVICES=0      # 서버 규칙: GPU 1장, 항상 지정
export OMP_NUM_THREADS=16          # 서버 규칙: CPU 스레드 합계 32 이하
export HF_HUB_OFFLINE=1            # 모델은 이미 받아 둔 것을 쓴다
kst() { TZ=Asia/Seoul date '+%F %T KST'; }
mkdir -p $D/logs
[ $# -eq 0 ] && { echo "사용법: bash run_v32.sh A B"; exit 1; }

for x in "$@"; do
  case $x in A|B) ;; *) echo "A 또는 B만 된다: $x"; exit 1;; esac
  run=v32$x-r16-e3
  [ -e $D/runs/$run ] && { echo "!! $D/runs/$run 이 이미 있다. 지우거나 이름을 바꾼 뒤 다시 실행"; exit 1; }
  echo "== $run 시작 $(kst)"
  nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
  python AI/train/train_qlora.py --run_name $run \
    --train $D/data/v32/sft_train_v3_2_$x.jsonl --valid $D/data/v32/sft_valid_v3_1.jsonl \
    --batch 4 --grad_accum 3 > $D/logs/$run.log 2>&1
  rc=$?
  echo "== $run 끝 (exit $rc) $(kst)"
  grep -E "eval_loss" $D/logs/$run.log | tail -3
  ls -d $D/runs/$run/checkpoint-* 2>/dev/null
  [ $rc -ne 0 ] && { echo "!! $run 실패. 로그 끝:"; tail -20 $D/logs/$run.log; exit $rc; }
done
echo "== 모두 끝 $(kst). 다음: bash ~/dgustu/code/AI/train/pack_v32.sh"
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
