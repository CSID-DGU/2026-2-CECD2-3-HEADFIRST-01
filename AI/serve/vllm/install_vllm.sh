#!/bin/bash
# vLLM 전용 venv (기존 qwen venv와 분리). 시험용.
export PATH="$HOME/.local/bin:$PATH"
export UV_PYTHON_INSTALL_DIR=/var/tmp/csuhyeon/python
export UV_CACHE_DIR=/var/tmp/csuhyeon/uv-cache
export UV_LINK_MODE=copy
VENV=/var/tmp/csuhyeon/venvs/vllm
kst() { TZ=Asia/Seoul date +%T; }
echo "== start $(kst)"
rm -rf "$VENV"
uv venv "$VENV" --python 3.12.15 || exit 1
source "$VENV/bin/activate"
echo "== install vllm $(kst)"
uv pip install "vllm==0.32.0" || exit 1
echo "== verify $(kst)"
python - <<'PY'
import torch, vllm, transformers
print("torch", torch.__version__, "| cuda", torch.version.cuda, "| gpus", torch.cuda.device_count())
print("vllm", vllm.__version__, "| transformers", transformers.__version__)
PY
echo "== venv size $(du -sh $VENV | cut -f1)"
echo "== DONE $(kst)"
# [farm7 patch] 이 Pod의 /dev/shm이 64MB뿐이라 TP 워커의 응답 큐(기본 24MB×10)를 1MB×10으로 줄인다
sed -i 's|max_chunk_bytes: int = 1024 \* 1024 \* 24,|max_chunk_bytes: int = 1024 * 1024 * 1,  # [farm7 patch] /dev/shm 64MB: 24MB->1MB|' \
  "$VENV/lib/python3.12/site-packages/vllm/distributed/device_communicators/shm_broadcast.py"
