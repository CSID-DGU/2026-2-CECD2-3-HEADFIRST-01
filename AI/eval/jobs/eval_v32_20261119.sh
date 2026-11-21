#!/bin/bash
# 2026-11-19: H200에서 학습한 v3.2 실험 A · B 어댑터(v32_adapters.tar)를 vLLM에 올리고 평가한다. vLLM은 끄지 않는다.
#   0) v32_adapters.tar의 sha256 확인 → runs/from_h200_v32/에 풀기
#   1) 키 이름 변환(add_adapter.sh) → 2) 서버를 켠 채로 어댑터 올리기(POST /v1/load_lora_adapter)
#   3) 확인: 어댑터 답이 학습 전 27B와 다른지(raw 테스트 62)
#   4) 하드 dev · test (score_hard.py score, compare --base A′) → 5) raw 테스트 62 · 실발화 227 · 생성 620
#   6) 보낼 파일 모으기: transfer/v32_results_20261119/ (dev 예측 파일 + 점수표. test 예측 파일은 넣지 않는다)
# 실험 A만 들어 있으면 A만 한다. 이미 평가한 실험은 건너뛴다(다시 하려면 runs/eval_vllm/v32X 를 지운다).
# 실행: setsid nohup bash eval_v32_20261119.sh > ~/capstone_design_2/runs/logs/eval_v32_20261119.log 2>&1 < /dev/null &
set -uo pipefail
R=~/capstone_design_2
E=$R/2026-2-CECD2-3-HEADFIRST-01/AI/eval
PY=$R/2026-2-CECD2-3-HEADFIRST-01/backend/.venv/bin/python
K=$R/hardset_eval_handoff_20261118
TAR=${TAR:-$R/v32_adapters.tar}
X=${X:-$R/runs/from_h200_v32}
P=${P:-v32}                      # vLLM 이름과 결과 폴더 앞부분 (시험할 때만 바꾼다)
AD=$HOME/var_tmp_backup_20261107/adapters
URL=http://localhost:8001
PKG=${PKG:-$R/transfer/v32_results_20261119}
export PYTHONDONTWRITEBYTECODE=1
kst() { TZ=Asia/Seoul date '+%F %T KST'; }
has_model() { curl -sf -m5 $URL/v1/models | grep -q "\"id\":\"$1\""; }

echo "== [0] 받은 파일 확인 $(kst)"
[ -f $TAR ] || { echo "!! $TAR 가 없다"; exit 1; }
if [ -f $TAR.sha256 ]; then
  (cd $(dirname $TAR) && sha256sum -c $(basename $TAR).sha256) || { echo "!! sha256 불일치. 다시 받아야 한다"; exit 1; }
else
  echo "(v32_adapters.tar.sha256 이 없어 지문 확인은 건너뜀)"
fi
mkdir -p $X && tar xf $TAR -C $X && tar tf $TAR
has_model Qwen3.8-27B || { echo "!! vLLM이 꺼져 있다"; exit 1; }

done_any=0
for pair in "A 1152" "B 1150"; do
  set -- $pair; x=$1; step=$2; name=$P$x
  ck=$X/runs/v32$x-r16-e3/checkpoint-$step
  O=$R/runs/eval_vllm/$name
  [ -d $ck ] || { echo "-- 실험 $x 어댑터 없음 ($ck), 건너뜀"; continue; }
  [ -f $O/gen620.log ] && grep -q "== 전체 ==" $O/gen620.log && { echo "-- 실험 $x 이미 평가함, 건너뜀"; done_any=1; continue; }
  mkdir -p $O/hard

  echo "== [1] 실험 $x 키 이름 변환 $(kst)"
  [ -d $AD/$name-ckpt$step-vl ] || bash $R/envs/vllm/add_adapter.sh $ck $name-ckpt$step || exit 1

  echo "== [2] 실험 $x vLLM에 올리기 (재시작 없음) $(kst)"
  if ! has_model $name; then
    curl -s -m300 -X POST $URL/v1/load_lora_adapter -H 'Content-Type: application/json' \
      -d "{\"lora_name\":\"$name\",\"lora_path\":\"$AD/$name-ckpt$step-vl\"}"; echo
  fi
  has_model $name || { echo "!! $name 이 vLLM 모델 목록에 없다"; exit 1; }

  echo "== [3] 실험 $x 어댑터 적용 확인 $(kst)"
  $PY $E/run_raw_test_vllm.py --kit $R/data/raw_elderly_v1 --model $name --out $O/raw62_check.jsonl > $O/raw62_check.log 2>&1
  python3 - "$R/runs/eval_vllm/base/raw62.jsonl" "$O/raw62_check.jsonl" <<'PY' || exit 1
import json, sys
a, c = ([json.loads(l)["raw"] for l in open(p)] for p in sys.argv[1:])
d = sum(x != z for x, z in zip(a, c))
print(f"어댑터 답이 학습 전 27B와 다른 문항: {d}/{len(a)}")
if d == 0:
    sys.exit("!! 답이 모두 같음 → 어댑터가 적용되지 않음. 평가 중단")
PY

  echo "== [4] 실험 $x 하드 테스트셋 $(kst)"
  for s in dev test; do
    $PY $E/run_hardset_vllm.py --kit $K --split $s --model $name --out $O/hard/pred_${s}_$name.jsonl
    python3 -B $K/score_hard.py score --pred $O/hard/pred_${s}_$name.jsonl > $O/hard/score_${s}_$name.txt 2>&1
    python3 -B $K/score_hard.py compare --base $R/runs/eval_vllm/Aprime/hard/pred_${s}_Aprime.jsonl \
      --model $O/hard/pred_${s}_$name.jsonl > $O/hard/compare_${s}_Aprime_vs_$name.txt 2>&1
    sed -n 1,7p $O/hard/score_${s}_$name.txt
  done

  echo "== [5] 실험 $x raw 테스트 62 · 실발화 227 · 생성 620 $(kst)"
  bash $E/eval_all_vllm.sh $name $name
  done_any=1
done
[ $done_any -eq 0 ] && { echo "!! 평가한 실험이 없다"; exit 1; }

echo "== [6] 보낼 파일 모으기 $(kst)"
mkdir -p $PKG/dev $PKG/test $PKG/existing
for name in ${P}A ${P}B; do
  O=$R/runs/eval_vllm/$name
  [ -f $O/gen620.log ] || continue
  cp $O/hard/pred_dev_$name.jsonl $O/hard/score_dev_$name.txt $O/hard/compare_dev_Aprime_vs_$name.txt $PKG/dev/
  cp $O/hard/score_test_$name.txt $O/hard/compare_test_Aprime_vs_$name.txt $PKG/test/   # test 예측 파일은 넣지 않는다
  cp $O/raw62.log $PKG/existing/score_raw62_$name.txt
  cp $O/real227.log $PKG/existing/score_real227_$name.txt
  cp $O/gen620.log $PKG/existing/score_gen620_$name.txt
done
(cd $(dirname $PKG) && tar czf $(basename $PKG).tar.gz $(basename $PKG))
find $PKG -type f | sort
echo "== ALL DONE $(kst)"
