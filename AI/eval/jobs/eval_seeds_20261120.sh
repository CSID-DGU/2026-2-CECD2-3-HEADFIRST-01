#!/bin/bash
# 2026-11-20: seed 추가 학습 어댑터(seeds_adapters.tar)를 11/19와 같은 조건(farm7 vLLM + fp8)으로 평가한다. vLLM은 끄지 않는다.
#   0) seeds_adapters.tar sha256 확인 → runs/from_h200_seeds/에 풀기
#   1) 어댑터마다: 키 이름 변환 → vLLM에 올리기(재시작 없음) → 적용 확인 → 하드 dev · test(compare --base A′)
#      → raw 테스트 62 · 실발화 227 · 생성 620 → raw val 62 → vLLM에서 내리기
#   2) 이미 있는 모델(학습 전 27B, A′, v32A, v32B)의 raw val 62 (아직 안 했으면)
#   3) 하드 test 정답 수 seed별 표 + 판단 기준 적용 → 4) 보낼 파일 모으기
# 끝난 어댑터는 건너뛴다(다시 하려면 runs/eval_vllm/<이름> 을 지운다). 묶음이 여러 번 와도 그때마다 실행하면 된다.
# 실행: setsid nohup bash eval_seeds_20261120.sh > ~/capstone_design_2/runs/logs/eval_seeds_20261120.log 2>&1 < /dev/null &
set -uo pipefail
R=~/capstone_design_2
E=${E:-$R/2026-2-CECD2-3-HEADFIRST-01/AI/eval}   # 저장소가 feat/eval-scripts가 아니면 E=runs/eval_code_feat_eval_scripts/AI/eval 로 준다
PY=$R/2026-2-CECD2-3-HEADFIRST-01/backend/.venv/bin/python
K=$R/hardset_eval_handoff_20261118
TAR=${TAR:-$R/seeds_adapters.tar}
X=${X:-$R/runs/from_h200_seeds}
PKG=${PKG:-$R/transfer/seeds_results_20261120}
AD=$HOME/var_tmp_backup_20261107/adapters
URL=http://localhost:8001
V=$R/runs/eval_vllm
export PYTHONDONTWRITEBYTECODE=1
kst() { TZ=Asia/Seoul date '+%F %T KST'; }
has_model() { curl -sf -m5 $URL/v1/models | grep -q "\"id\":\"$1\""; }
need_27b() { has_model Aprime || { echo "!! 27B vLLM(Aprime)이 없다. 14B 평가 등으로 꺼져 있으면 끝난 뒤 다시 실행"; exit 1; }; }
rawval() {   # rawval <vLLM 이름> <결과 폴더>
  [ -f $2/rawval62.log ] && grep -q "macro-F1" $2/rawval62.log && return 0
  $PY $E/run_raw_test_vllm.py --kit $R/data/raw_elderly_v1 --data raw_노인_val.jsonl --model $1 \
    --out $2/rawval62.jsonl > $2/rawval62.log 2>&1
  echo "  raw val 62 ($1): $(grep macro-F1 $2/rawval62.log)"
}

echo "== [0] 받은 파일 확인 $(kst)"
need_27b
if [ -f $TAR ]; then
  (cd $(dirname $TAR) && sha256sum -c $(basename $TAR).sha256) || { echo "!! sha256 불일치. 다시 받아야 한다"; exit 1; }
  mkdir -p $X && tar xf $TAR -C $X && tar tf $TAR | grep safetensors
else
  echo "-- $TAR 없음 (이미 있는 모델의 raw val 62와 표만 만든다)"
fi

# H200 학습 이름 → vLLM 이름. Ap42h = 11/18 H200 A′ 재학습(seed 42, 참고용)
for pair in "v31-r16-e3 842 Ap42h" "v31-r16-e3-s43 842 Aps43" "v31-r16-e3-s44 842 Aps44" \
            "v32A-r16-e3-s43 1152 v32As43" "v32A-r16-e3-s44 1152 v32As44" \
            "v32B-r16-e3-s43 1150 v32Bs43" "v32B-r16-e3-s44 1150 v32Bs44"; do
  set -- $pair; run=$1; step=$2; name=$3
  ck=$X/runs/$run/checkpoint-$step; O=$V/$name
  [ -f $ck/adapter_model.safetensors ] || continue
  if [ -f $O/gen620.log ] && grep -q "== 전체 ==" $O/gen620.log && [ -f $O/rawval62.log ]; then echo "-- $name 이미 평가함, 건너뜀"; continue; fi
  echo "== [1] $name ($run/checkpoint-$step) $(kst)"
  need_27b
  [ -d $AD/$name-ckpt$step-vl ] || bash $R/envs/vllm/add_adapter.sh $ck $name-ckpt$step || exit 1
  has_model $name || curl -s -m300 -X POST $URL/v1/load_lora_adapter -H 'Content-Type: application/json' \
    -d "{\"lora_name\":\"$name\",\"lora_path\":\"$AD/$name-ckpt$step-vl\"}"; echo
  has_model $name || { echo "!! $name 이 vLLM에 없다"; exit 1; }
  mkdir -p $O/hard
  $PY $E/run_raw_test_vllm.py --kit $R/data/raw_elderly_v1 --model $name --out $O/raw62_check.jsonl > $O/raw62_check.log 2>&1
  python3 - "$V/base/raw62.jsonl" "$O/raw62_check.jsonl" <<'PYC' || exit 1
import json, sys
a, c = ([json.loads(l)["raw"] for l in open(p)] for p in sys.argv[1:])
d = sum(x != z for x, z in zip(a, c))
print(f"  어댑터 답이 학습 전 27B와 다른 문항: {d}/{len(a)}")
if d == 0:
    sys.exit("!! 답이 모두 같음 → 어댑터가 적용되지 않음. 평가 중단")
PYC
  for s in dev test; do
    $PY $E/run_hardset_vllm.py --kit $K --split $s --model $name --out $O/hard/pred_${s}_$name.jsonl
    python3 -B $K/score_hard.py score --pred $O/hard/pred_${s}_$name.jsonl > $O/hard/score_${s}_$name.txt 2>&1
    python3 -B $K/score_hard.py compare --base $V/Aprime/hard/pred_${s}_Aprime.jsonl \
      --model $O/hard/pred_${s}_$name.jsonl > $O/hard/compare_${s}_Aprime_vs_$name.txt 2>&1
    echo "  하드 $s: $(grep -E '문제 정답률' $O/hard/score_${s}_$name.txt)"
  done
  bash $E/eval_all_vllm.sh $name $name
  rawval $name $O
  curl -s -X POST $URL/v1/unload_lora_adapter -H 'Content-Type: application/json' -d "{\"lora_name\":\"$name\"}"; echo
done

echo "== [2] 이미 있는 모델의 raw val 62 $(kst)"
need_27b
rawval Qwen3.8-27B $V/base
for n in Aprime v32A v32B; do rawval $n $V/$n; done

echo "== [3] 하드 test 정답 수 seed별 표 $(kst)"
mkdir -p $PKG
python3 - "$V" > $PKG/SUMMARY_hard_test_seeds.md <<'PYS'
import re, sys
from pathlib import Path
V = Path(sys.argv[1])
def get(name, split="test"):
    p = V / name / "hard" / f"score_{split}_{name}.txt"
    if not p.exists(): return None
    t = p.read_text()
    ok = int(re.search(r"문제 정답률: (\d+)/", t).group(1)); f1 = float(re.search(r"macro-F1: ([0-9.]+)", t).group(1))
    return ok, f1
groups = [("A′ (v3.1)", [("Aprime", "42 (farm7)"), ("Aps43", "43"), ("Aps44", "44")]),
          ("v3.2 A", [("v32A", "42"), ("v32As43", "43"), ("v32As44", "44")]),
          ("v3.2 B", [("v32B", "42"), ("v32Bs43", "43"), ("v32Bs44", "44")])]
print("# 하드 test 200 정답 수 (seed별)\n")
print("| 학습 데이터 | seed | 하드 test 정답 수 | macro-F1 | 하드 dev 정답 수 |\n|---|---|---:|---:|---:|")
rng = {}
for g, items in groups:
    oks = []
    for name, seed in items:
        r = get(name); d = get(name, "dev")
        if r: oks.append(r[0])
        print(f"| {g} | {seed} | {r[0] if r else '(아직)'} | {r[1] if r else ''} | {d[0] if d else ''} |")
    if len(oks) == 3: rng[g] = (min(oks), max(oks))
ref = get("Ap42h")
if ref: print(f"| (참고) A′ H200 재학습 | 42 (H200) | {ref[0]} | {ref[1]} | {get('Ap42h','dev')[0]} |")
print("\n## 판단 기준 (결과 확인 전에 확정): 하드 test 정답 수의 seed 3개 범위가 A′와 겹치지 않으면 v3.2를 메인으로 채택, 겹치면 차이 없음 → A′ 유지\n")
if "A′ (v3.1)" not in rng:
    print("- A′ seed 3개가 아직 다 없어서 판단 보류"); sys.exit()
a0, a1 = rng["A′ (v3.1)"]
print(f"- A′ 범위: {a0} ~ {a1}")
for g in ("v3.2 A", "v3.2 B"):
    if g not in rng: print(f"- {g}: seed 3개가 아직 다 없어서 판단 보류"); continue
    b0, b1 = rng[g]
    verdict = "A′ 범위보다 위 → 채택 기준 충족" if b0 > a1 else ("A′ 범위보다 아래 → A′ 유지" if b1 < a0 else "A′ 범위와 겹침 → 차이 없음, A′ 유지")
    print(f"- {g} 범위: {b0} ~ {b1} → {verdict}")
PYS
cat $PKG/SUMMARY_hard_test_seeds.md

echo "== [4] 보낼 파일 모으기 $(kst)"
mkdir -p $PKG/dev $PKG/test $PKG/raw62 $PKG/rawval62 $PKG/existing
for name in Aps43 Aps44 Ap42h v32As43 v32As44 v32Bs43 v32Bs44; do
  O=$V/$name; [ -f $O/gen620.log ] || continue
  cp $O/hard/pred_dev_$name.jsonl $O/hard/score_dev_$name.txt $O/hard/compare_dev_Aprime_vs_$name.txt $PKG/dev/
  cp $O/hard/score_test_$name.txt $O/hard/compare_test_Aprime_vs_$name.txt $PKG/test/    # test 예측 파일은 넣지 않는다
  cp $O/raw62.log $PKG/raw62/score_raw62_$name.txt                                       # raw 62도 test: 점수표만
  cp $O/real227.log $PKG/existing/score_real227_$name.txt
  cp $O/gen620.log $PKG/existing/score_gen620_$name.txt
done
for pair in "base untrained" "Aprime Aprime" "v32A v32A" "v32B v32B" "Aps43 Aps43" "Aps44 Aps44" "Ap42h Ap42h" \
            "v32As43 v32As43" "v32As44 v32As44" "v32Bs43 v32Bs43" "v32Bs44 v32Bs44"; do
  set -- $pair; O=$V/$1
  [ -f $O/rawval62.jsonl ] || continue
  cp $O/rawval62.jsonl $PKG/rawval62/pred_rawval62_$2.jsonl                              # val은 예측 파일도 보낸다
  cp $O/rawval62.log $PKG/rawval62/score_rawval62_$2.txt
done
(cd $(dirname $PKG) && tar czf $(basename $PKG).tar.gz $(basename $PKG))
find $PKG -type f | sort
echo "== ALL DONE $(kst)"
