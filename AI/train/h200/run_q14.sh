#!/bin/bash
# Qwen3-14B를 v3.2 실험 B · A 데이터로, 27B(v32A · v32B)와 같은 조건으로 학습한다 (H200 GPU 0번 1장).
#   같은 조건: train_qlora.py 기본값(4bit QLoRA nf4, r 16, alpha 32, lr 2e-4, max_len 1024, 3에폭, seed 42),
#             실효 배치 12(--batch 4 --grad_accum 3), 검증 sft_valid_v3_1.jsonl
#   바뀐 것: 모델만 (--model Qwen/Qwen3-14B)
# 실행 (tmux 안에서):
#   bash ~/dgustu/code/AI/train/run_q14.sh smoke     ← 먼저 6스텝 시험 (약 2~3분)
#   bash ~/dgustu/code/AI/train/run_q14.sh B A       ← 시험이 통과하면 본 학습. B 다음 A
# 결과: ~/dgustu/runs/q14-v32B-r16-e3/checkpoint-{575,1150,1725}, ~/dgustu/runs/q14-v32A-r16-e3/checkpoint-{576,1152,1728}
# 로그: ~/dgustu/logs/q14-*.log
set -uo pipefail
D=$HOME/dgustu
source $D/envs/qwen/bin/activate
cd $D/code
export CUDA_VISIBLE_DEVICES=0      # 서버 규칙: GPU 1장, 항상 지정
export OMP_NUM_THREADS=16          # 서버 규칙: CPU 스레드 합계 32 이하
export HF_HUB_OFFLINE=1            # 모델은 미리 받아 둔 것을 쓴다
M=Qwen/Qwen3-14B
kst() { TZ=Asia/Seoul date '+%F %T KST'; }
mkdir -p $D/logs
[ $# -eq 0 ] && { echo "사용법: bash run_q14.sh smoke  또는  bash run_q14.sh B A"; exit 1; }
REF=$HF_HOME/hub/models--Qwen--Qwen3-14B/refs/main
[ -f $REF ] || { echo "!! $M 원본이 없다. 먼저: hf download $M"; exit 1; }
echo "모델 $M revision $(cat $REF)"

for x in "$@"; do
  case $x in
    smoke) run=q14-smoke; extra="--max_train 48 --max_valid 8 --max_steps 6 --grad_accum 2 --eval_every 6"
           data=$D/data/v32/sft_train_v3_2_B.jsonl; rm -rf $D/runs/$run ;;
    A|B)   run=q14-v32$x-r16-e3; extra="--grad_accum 3"; data=$D/data/v32/sft_train_v3_2_$x.jsonl
           [ -e $D/runs/$run ] && { echo "!! $D/runs/$run 이 이미 있다. 지우거나 이름을 바꾼 뒤 다시 실행"; exit 1; } ;;
    *) echo "smoke, A, B만 된다: $x"; exit 1 ;;
  esac
  echo "== $run 시작 $(kst)"
  nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
  python AI/train/train_qlora.py --model $M --run_name $run \
    --train $data --valid $D/data/v32/sft_valid_v3_1.jsonl --batch 4 $extra > $D/logs/$run.log 2>&1
  rc=$?
  echo "== $run 끝 (exit $rc) $(kst)"
  grep -E "trainable params|\[mem\]" $D/logs/$run.log | head -3
  grep -o "'eval_loss': '[0-9.e-]*'" $D/logs/$run.log
  ls -d $D/runs/$run/checkpoint-* 2>/dev/null
  [ $rc -ne 0 ] && { echo "!! $run 실패. 로그 끝:"; tail -20 $D/logs/$run.log; exit $rc; }
done
echo "== 모두 끝 $(kst)"
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
