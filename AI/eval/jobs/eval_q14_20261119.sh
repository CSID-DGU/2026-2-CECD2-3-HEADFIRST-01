#!/bin/bash
# 2026-11-19: H200에서 학습한 14B 어댑터(q14_adapters.tar)를 평가한다. GPU 2장에는 모델을 하나만 올릴 수 있어서
# 27B vLLM을 끄고(백엔드 멈춤) 14B vLLM을 띄운다. 끝나면(실패해도) 27B vLLM을 다시 켠다.
#   0) q14_adapters.tar sha256 확인 → runs/from_h200_q14/에 풀기 → 키 이름 확인(add_adapter.sh, 14B는 바꾸지 않음)
#   1) 27B vLLM 끄기 → 2) 14B vLLM 켜기(serve_vllm_14b.sh + --lora-modules)
#   3) 학습 전 14B 평가(이미 했으면 건너뜀): 하드 dev · test, raw 테스트 62 · 실발화 227 · 생성 620
#   4) 어댑터마다: 적용 확인(raw 62 답이 학습 전 14B와 다른지) → 하드 dev · test(compare: 학습 전 14B 대비, 같은 데이터 27B 대비)
#      → raw 62 · 실발화 227 · 생성 620 → 응답 속도(LAT=1일 때)
#   5) 보낼 파일 모으기 → 6) 14B 끄고 27B vLLM 다시 켜기
# 실행: setsid nohup bash eval_q14_20261119.sh > ~/capstone_design_2/runs/logs/eval_q14_20261119.log 2>&1 < /dev/null &
set -uo pipefail
R=~/capstone_design_2
E=$R/2026-2-CECD2-3-HEADFIRST-01/AI/eval
PY=$R/2026-2-CECD2-3-HEADFIRST-01/backend/.venv/bin/python
K=$R/hardset_eval_handoff_20261118
TAR=${TAR:-$R/q14_adapters.tar}
X=${X:-$R/runs/from_h200_q14}
P=${P:-q14}                       # vLLM 이름과 결과 폴더 앞부분 (시험할 때만 바꾼다)
PKG=${PKG:-$R/transfer/q14_results_20261119}
LAT=${LAT:-1}                     # 1이면 어댑터마다 응답 속도도 잰다 (약 6분)
AD=$HOME/var_tmp_backup_20261107/adapters
URL=http://localhost:8001
LOG14=/var/tmp/csuhyeon/serve_vllm_14b.log
BASE=$R/runs/eval_vllm/q14base    # 학습 전 14B 결과 (한 번만 잰다)
export PYTHONDONTWRITEBYTECODE=1
kst() { TZ=Asia/Seoul date '+%F %T KST'; }
has_model() { curl -sf -m5 $URL/v1/models | grep -q "\"id\":\"$1\""; }
vpid() { pgrep -f "^/var/tmp/csuhyeon/venvs/vllm/bin/python .*vllm serve" | head -1; }
wait_down() { for i in $(seq 60); do [ -z "$(vpid)" ] && break; sleep 5; done; sleep 10; }

echo "== [0] 받은 파일 확인 $(kst)"
[ -f $TAR ] || { echo "!! $TAR 가 없다"; exit 1; }
(cd $(dirname $TAR) && sha256sum -c $(basename $TAR).sha256) || { echo "!! sha256 불일치. 다시 받아야 한다"; exit 1; }
mkdir -p $X && tar xf $TAR -C $X && tar tf $TAR
names=(); mods=()
for pair in "B 1150" "A 1152"; do
  set -- $pair; x=$1; step=$2; name=$P$x
  ck=$X/runs/q14-v32$x-r16-e3/checkpoint-$step
  [ -d $ck ] || { echo "-- 14B 실험 $x 어댑터 없음, 건너뜀"; continue; }
  [ -d $AD/$name-ckpt$step-vl ] || bash $R/envs/vllm/add_adapter.sh $ck $name-ckpt$step || exit 1
  names+=($name); mods+=("$name=$AD/$name-ckpt$step-vl")
done
[ ${#names[@]} -eq 0 ] && { echo "!! 평가할 어댑터가 없다"; exit 1; }
echo "평가할 어댑터: ${names[*]}"

restart_27b() {
  echo "== [6] 14B 끄고 27B vLLM 다시 켜기 $(kst)"
  p=$(vpid); [ -n "$p" ] && kill "$p"; wait_down
  bash /var/tmp/csuhyeon/vllm_ctl.sh start
  for i in $(seq 120); do has_model Aprime && break; sleep 5; done
  echo "27B: $(bash /var/tmp/csuhyeon/vllm_ctl.sh status | head -1) $(kst)"
}

echo "== [1] 27B vLLM 끄기 (백엔드 멈춤) $(kst)"
trap restart_27b EXIT
bash /var/tmp/csuhyeon/vllm_ctl.sh stop; wait_down

echo "== [2] 14B vLLM 켜기 $(kst)"
nohup bash $R/envs/vllm/serve_vllm_14b.sh --lora-modules "${mods[@]}" > $LOG14 2>&1 &
for i in $(seq 180); do
  has_model ${names[-1]} && break
  [ -z "$(vpid)" ] && [ $i -gt 6 ] && break
  sleep 5
done
for n in Qwen3-14B "${names[@]}"; do has_model $n || { echo "!! $n 이 준비되지 않음"; tail -30 $LOG14; exit 1; }; done
echo "14B 준비됨 $(kst): $(curl -s $URL/v1/models | python3 -c 'import json,sys; print([m["id"] for m in json.load(sys.stdin)["data"]])')"

hard() {   # hard <vLLM 이름> <결과 폴더>
  mkdir -p $2/hard
  for s in dev test; do
    $PY $E/run_hardset_vllm.py --kit $K --split $s --model $1 --out $2/hard/pred_${s}_$1.jsonl
    python3 -B $K/score_hard.py score --pred $2/hard/pred_${s}_$1.jsonl > $2/hard/score_${s}_$1.txt 2>&1
    grep -E "문제 정답률|macro-F1" $2/hard/score_${s}_$1.txt
  done
}

echo "== [3] 학습 전 14B $(kst)"
if [ -f $BASE/gen620.log ] && grep -q "== 전체 ==" $BASE/gen620.log; then
  echo "-- 이미 평가함, 건너뜀 ($BASE)"
else
  hard Qwen3-14B $BASE
  bash $E/eval_all_vllm.sh Qwen3-14B q14base
fi

for name in "${names[@]}"; do
  x=${name: -1}; O=$R/runs/eval_vllm/$name
  echo "== [4] 14B 실험 $x ($name) $(kst)"
  mkdir -p $O
  $PY $E/run_raw_test_vllm.py --kit $R/data/raw_elderly_v1 --model $name --out $O/raw62_check.jsonl > $O/raw62_check.log 2>&1
  python3 - "$BASE/raw62.jsonl" "$O/raw62_check.jsonl" <<'PYC' || exit 1
import json, sys
a, c = ([json.loads(l)["raw"] for l in open(p)] for p in sys.argv[1:])
d = sum(x != z for x, z in zip(a, c))
print(f"어댑터 답이 학습 전 14B와 다른 문항: {d}/{len(a)}")
if d == 0:
    sys.exit("!! 답이 모두 같음 → 어댑터가 적용되지 않음. 평가 중단")
PYC
  hard $name $O
  for s in dev test; do
    python3 -B $K/score_hard.py compare --base $BASE/hard/pred_${s}_Qwen3-14B.jsonl --model $O/hard/pred_${s}_$name.jsonl \
      > $O/hard/compare_${s}_q14base_vs_$name.txt 2>&1
    b27=$R/runs/eval_vllm/v32$x/hard/pred_${s}_v32$x.jsonl
    [ -f $b27 ] && python3 -B $K/score_hard.py compare --base $b27 --model $O/hard/pred_${s}_$name.jsonl \
      > $O/hard/compare_${s}_v32${x}_vs_$name.txt 2>&1
  done
  bash $E/eval_all_vllm.sh $name $name
  if [ "$LAT" = 1 ]; then
    echo "-- 응답 속도 $(kst)"
    $PY $E/latency_vllm.py --model $name --tag 14b-$name > $R/runs/logs/latency-14b-$name.log 2>&1
    grep -E "^\[conc" $R/runs/logs/latency-14b-$name.log
  fi
done

echo "== [5] 보낼 파일 모으기 $(kst)"
mkdir -p $PKG/dev $PKG/test $PKG/existing
for name in Qwen3-14B "${names[@]}"; do
  [ $name = Qwen3-14B ] && O=$BASE || O=$R/runs/eval_vllm/$name
  cp $O/hard/pred_dev_$name.jsonl $O/hard/score_dev_$name.txt $PKG/dev/
  cp $O/hard/score_test_$name.txt $PKG/test/          # test 예측 파일은 넣지 않는다
  cp $O/hard/compare_dev_*_vs_$name.txt $PKG/dev/ 2>/dev/null
  cp $O/hard/compare_test_*_vs_$name.txt $PKG/test/ 2>/dev/null
  t=$([ $name = Qwen3-14B ] && echo q14base || echo $name)
  cp $O/raw62.log $PKG/existing/score_raw62_$t.txt
  cp $O/real227.log $PKG/existing/score_real227_$t.txt
  cp $O/gen620.log $PKG/existing/score_gen620_$t.txt
done
(cd $(dirname $PKG) && tar czf $(basename $PKG).tar.gz $(basename $PKG))
find $PKG -type f | sort
echo "== ALL DONE (27B 다시 켜기 전) $(kst)"
