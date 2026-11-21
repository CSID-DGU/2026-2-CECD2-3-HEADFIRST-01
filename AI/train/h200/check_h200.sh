#!/bin/bash
# H200(nvl03, 공유 계정 iot3)에서 v3.2 학습 전에 환경을 점검한다. 아무것도 바꾸지 않고 읽기만 한다.
# 실행: bash ~/dgustu/code/AI/train/check_h200.sh
# 끝에 [OK] / [확인 필요] 목록이 나온다. [확인 필요]가 있으면 학습을 시작하지 않는다.
D=$HOME/dgustu
CODE=$D/code
VENV=$D/envs/qwen
problems=()
ok()   { echo "  [OK] $*"; }
warn() { echo "  [확인 필요] $*"; problems+=("$*"); }

echo "== 1. 폴더와 파일"
for p in $CODE/AI/.env $CODE/AI/train/train_qlora.py $D/data/v32/sft_train_v3_2_A.jsonl \
         $D/data/v32/sft_train_v3_2_B.jsonl $D/data/v32/sft_valid_v3_1.jsonl; do
  [ -f "$p" ] && ok "$p" || warn "$p 가 없다"
done
grep -q "dgustu" $CODE/AI/.env 2>/dev/null && ok "AI/.env 경로가 ~/dgustu 안이다" || warn "AI/.env 경로 확인"

echo "== 2. 학습 데이터가 farm7에서 보낸 것과 같은지 (sha256)"
(cd $D/data/v32 && sha256sum -c SHA256SUMS) && ok "데이터 3개 일치" || warn "데이터가 다르다 (옮기는 중에 깨졌을 수 있다)"
for f in A B; do echo "  sft_train_v3_2_$f.jsonl: $(wc -l < $D/data/v32/sft_train_v3_2_$f.jsonl)줄"; done

echo "== 3. 가상환경과 라이브러리 버전"
if [ -f $VENV/bin/activate ]; then
  source $VENV/bin/activate
  python - <<'PY' || echo "  [확인 필요] 라이브러리를 불러오지 못함"
import importlib
for m in ["torch", "transformers", "peft", "trl", "bitsandbytes", "accelerate", "tilelang"]:
    try:
        mod = importlib.import_module(m); print(f"  {m:13s} {getattr(mod, '__version__', '?')}")
    except Exception as e:
        print(f"  [확인 필요] {m} 불러오기 실패: {e}")
import torch
print(f"  CUDA 사용 가능: {torch.cuda.is_available()}, torch CUDA {torch.version.cuda}")
PY
  ok "가상환경 $VENV"
else
  warn "가상환경 $VENV 가 없다 → setup_h200.sh를 다시 실행"
fi

echo "== 4. 모델 원본 (Qwen/Qwen3.8-27B)"
M=$D/cache/hf/hub/models--Qwen--Qwen3.8-27B
if [ -d $M/snapshots ]; then
  echo "  refs/main: $(cat $M/refs/main 2>/dev/null)"
  for s in $M/snapshots/*; do
    n=$(ls $s | grep -c '\.safetensors$'); echo "  $(basename $s): safetensors $n개, $(du -shL $s | cut -f1)"
  done
  ok "모델 원본 있음"
else
  warn "모델 원본이 없다 ($M)"
fi

echo "== 5. GPU (우리가 쓰는 것은 GPU 0번 1장)"
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader
used0=$(nvidia-smi --id=0 --query-gpu=memory.used --format=csv,noheader,nounits | tr -d ' ')
[ "${used0:-99999}" -lt 2000 ] && ok "GPU 0번이 비어 있다 (${used0} MiB)" || warn "GPU 0번을 누군가 쓰고 있다 (${used0} MiB). 다른 빈 GPU가 있으면 담당자에게 알리고 쓴다"

echo "== 6. 내 프로세스 (서버 매뉴얼 방식: 작업 폴더가 dgustu 안인 프로세스. 셸과 이 점검 스크립트는 뺀다)"
mine=0
for p in /proc/[0-9]*; do
  cwd=$(readlink $p/cwd 2>/dev/null) || continue
  case "$cwd" in *dgustu*) ;; *) continue;; esac
  cmd=$(tr '\0' ' ' < $p/cmdline 2>/dev/null)
  case "$cmd" in -bash*|bash\ |/bin/bash\ --init-file*|*check_h200.sh*|"") continue;; esac
  echo "  PID ${p#/proc/}: $(echo "$cmd" | cut -c1-100)"; mine=$((mine+1))
done
[ $mine -eq 0 ] && ok "남아 있는 내 작업 없음" || warn "내 프로세스가 남아 있다. 이전 학습이면 kill <PID>로 끈다 (pkill 금지)"

echo "== 7. 디스크 (~/dgustu는 /data2)"
df -h $D | tail -1
du -sh $D/runs/* 2>/dev/null | sed 's/^/  /'
echo "  끝난 학습의 체크포인트는 지우는 것이 서버 규칙이다 (필요한 어댑터는 먼저 노트북으로 옮긴다)"

echo "== 8. tmux"
command -v tmux >/dev/null && ok "tmux 있음" || warn "tmux가 없다"
tmux ls 2>/dev/null | grep dgustu | sed 's/^/  /'

echo
if [ ${#problems[@]} -eq 0 ]; then echo "== 결과: 모두 OK. 학습을 시작해도 된다"
else echo "== 결과: 확인 필요 ${#problems[@]}개"; printf '  - %s\n' "${problems[@]}"; fi
