#!/usr/bin/env bash
# farm7 vLLM(8001)에 떠 있는 모델 하나로 평가셋 3종을 차례로 푼다. 결과는 runs/eval_vllm/<태그>/ 에 남는다.
# 용도: vLLM 서버로 옮긴 뒤(2026-10-28 이후) 어댑터를 새로 올릴 때마다 기본 평가 3종을 같은 조건으로 다시 잰다.
#   bash eval_all_vllm.sh <vLLM 모델 이름> [태그]
#   예) bash eval_all_vllm.sh Qwen3.8-27B base      (학습 전)
#       bash eval_all_vllm.sh v31 v31-ep2           (serve_vllm.sh에 v31로 등록한 어댑터)
# 620: check_responses.py (멘토 채점기, 프롬프트 auto=v2, temperature 0)
# 227: run_track1_v01.py base 모드 (testset_v0_1.jsonl)
# 62 : run_raw_test_vllm.py (raw_노인_test.jsonl, evaluate_raw.py 채점)
set -uo pipefail
MODEL=${1:?vLLM 모델 이름}
TAG=${2:-$MODEL}
ROOT=~/capstone_design_2
DATA=$ROOT/data
OUT=$ROOT/runs/eval_vllm/$TAG
PY=$ROOT/2026-2-CECD2-3-HEADFIRST-01/backend/.venv/bin/python   # openai 패키지가 있는 venv (run_track1_v01.py용)
URL=http://localhost:8001/v1
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$OUT"

curl -sf -m5 $URL/models | grep -q "\"id\":\"$MODEL\"" || { echo "vLLM에 '$MODEL'이 없다 (curl $URL/models 확인)"; exit 1; }
echo "== $(date '+%F %T') model=$MODEL -> $OUT"

echo "== [1/3] raw test 62"
$PY "$(dirname "$0")/run_raw_test_vllm.py" --kit $DATA/raw_elderly_v1 --model "$MODEL" \
  --out $OUT/raw62.jsonl > $OUT/raw62.log 2>&1
tail -25 $OUT/raw62.log

echo "== [2/3] 실발화 227"
(cd $DATA/eval_real && $PY run_track1_v01.py --base-url $URL --model "$MODEL" --mode base \
  --data testset_v0_1.jsonl --out $OUT/real227.jsonl) > $OUT/real227.log 2>&1
tail -8 $OUT/real227.log

echo "== [3/3] 생성 620"
$PY $DATA/eval_mini/check_responses.py --data $DATA/eval_full/minwon_eval_v2.json --base-url $URL \
  --model "$MODEL" --temperature 0 --workers 8 --out $OUT/gen620.jsonl > $OUT/gen620.log 2>&1
grep -A6 "== 전체 ==" $OUT/gen620.log

echo "== $(date '+%F %T') 끝"
