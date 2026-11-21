#!/bin/bash
# 14B 학습이 끝난 어댑터 중 에폭 2 체크포인트만 묶어 farm7로 보낼 파일을 만든다 (pack_v32.sh의 14B판).
# 실행: bash ~/dgustu/code/AI/train/pack_q14.sh   → ~/dgustu/results/q14_adapters.tar
set -euo pipefail
D=$HOME/dgustu
OUT=$D/results/q14_adapters.tar
mkdir -p $D/results
files=()
for pair in "q14-v32B-r16-e3 1150" "q14-v32A-r16-e3 1152"; do
  set -- $pair; run=$1; step=$2
  c=runs/$run/checkpoint-$step
  if [ -d $D/$c ]; then
    for f in adapter_config.json adapter_model.safetensors trainer_state.json; do files+=("$c/$f"); done
    [ -f $D/logs/$run.log ] && files+=("logs/$run.log")
  else
    echo "!! $D/$c 가 없다 (아직 학습 중이거나 스텝 수가 다르다: ls $D/runs/$run)"
  fi
done
[ ${#files[@]} -eq 0 ] && { echo "묶을 것이 없다"; exit 1; }
tar cf $OUT -C $D "${files[@]}"
(cd $D/results && sha256sum q14_adapters.tar > q14_adapters.tar.sha256)
tar tvf $OUT
echo "== $OUT ($(du -h $OUT | cut -f1)), sha256: $(cut -d' ' -f1 $OUT.sha256)"
echo "노트북으로 내려받아 farm7 ~/capstone_design_2/ 에 올린다."
