#!/bin/bash
# 학습용 가상환경을 로컬 디스크(AI/.env의 LOCAL_ROOT)에 만든다.
# - 로컬 디스크는 빠르지만 Pod가 재시작되면 지워질 수 있다 → 그때 이 스크립트를 다시 실행한다.
# - 모델 원본은 HF_HOME, 학습 결과 보관은 RUNS_ARCHIVE (둘 다 AI/.env에서 지정).
# 사용법 (레포 어디서 실행해도 됨):
#   bash AI/train/setup_local_venv.sh
set -u
TRAIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # 이 스크립트가 있는 AI/train
ENV_FILE="$TRAIN_DIR/../.env"                                # AI/.env

# 1) AI/.env 읽기 + 빈 값 검사
if [ ! -f "$ENV_FILE" ]; then
  echo "AI/.env가 없다. AI/.env.example을 복사해 AI/.env를 만들고 경로를 채운 뒤 다시 실행한다." >&2
  exit 1
fi
set -a; source "$ENV_FILE"; set +a
missing=""
for v in HF_HOME LOCAL_ROOT RUNS_ARCHIVE; do
  [ -z "${!v:-}" ] && missing="$missing $v"
done
if [ -n "$missing" ]; then
  echo "AI/.env에 값이 비어 있다:$missing" >&2
  exit 1
fi

VENV="$LOCAL_ROOT/venvs/qwen"
export PATH="$HOME/.local/bin:/usr/local/cuda/bin:$PATH"
export UV_PYTHON_INSTALL_DIR="$LOCAL_ROOT/python"    # 파이썬 본체도 로컬에
export UV_CACHE_DIR="${UV_CACHE_DIR:-$LOCAL_ROOT/uv-cache}"
export UV_LINK_MODE=copy
mkdir -p "$LOCAL_ROOT/venvs" "$LOCAL_ROOT/hf-datasets" "$HF_HOME" "$RUNS_ARCHIVE"
kst() { TZ=Asia/Seoul date +%T; }

if ! command -v uv >/dev/null; then
  echo "uv가 없다. 먼저 설치한다: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

echo "== start KST $(kst) | LOCAL_ROOT=$LOCAL_ROOT | HF_HOME=$HF_HOME"
uv python install 3.12.15 || exit 1
rm -rf "$VENV"
uv venv "$VENV" --python 3.12.15 || exit 1

# 가상환경을 켜면 모델 위치와 캐시 위치도 함께 잡히도록 activate 끝에 덧붙인다.
cat >> "$VENV/bin/activate" <<ACT

# --- 프로젝트 설정 (setup_local_venv.sh가 AI/.env 값으로 작성) ---
export HF_HOME="$HF_HOME"
export HF_DATASETS_CACHE="$LOCAL_ROOT/hf-datasets"
export CUDA_HOME=/usr/local/cuda
export PATH=/usr/local/cuda/bin:\$PATH
ACT
source "$VENV/bin/activate"

# 2) PyTorch(CUDA 12.8 빌드)를 먼저, 나머지를 그 다음에 설치한다.
#    한 번에 설치하면 PyPI의 다른 CUDA 빌드로 바뀔 수 있어 두 단계로 나눈다.
echo "== step1 torch cu128 KST $(kst)"
uv pip install -r "$TRAIN_DIR/requirements-torch-cu128.txt" --index-url https://download.pytorch.org/whl/cu128 || exit 1
echo "== step2 libs KST $(kst)"
uv pip install -r "$TRAIN_DIR/requirements-libs.txt" || exit 1

# 3) causal-conv1d: Qwen3.8의 Gated DeltaNet 층용 고속 커널. A5000(sm_86)용으로 직접 컴파일한다.
echo "== step3 causal-conv1d KST $(kst)"
uv pip install ninja packaging setuptools wheel
mkdir -p "$LOCAL_ROOT/build-tmp"
TORCH_CUDA_ARCH_LIST="8.6" MAX_JOBS=6 CAUSAL_CONV1D_FORCE_BUILD=TRUE TMPDIR="$LOCAL_ROOT/build-tmp" \
  uv pip install --no-build-isolation causal-conv1d \
  || echo "!! causal-conv1d 설치 실패 (학습은 가능, 느린 기본 구현 사용)"
rm -rf "$LOCAL_ROOT/build-tmp"

# 4) 확인
echo "== verify KST $(kst)"
python - <<'PY'
import torch
print("torch", torch.__version__, "| cuda", torch.version.cuda, "| gpus", torch.cuda.device_count(), "| bf16", torch.cuda.is_bf16_supported())
for m in ["transformers", "peft", "trl", "bitsandbytes", "accelerate", "datasets", "fla", "causal_conv1d", "dotenv"]:
    try:
        mod = __import__(m); print(m, getattr(mod, "__version__", "ok"))
    except Exception as e:
        print(m, "IMPORT FAILED:", repr(e)[:150])
PY
echo "== venv size $(du -sh "$VENV" | cut -f1)"
echo "== ALL DONE KST $(kst)"
echo "가상환경 켜기: source $VENV/bin/activate"
