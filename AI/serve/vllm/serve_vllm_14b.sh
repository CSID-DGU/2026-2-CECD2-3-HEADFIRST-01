#!/bin/bash
# 2026-11-19: 14B 응답 속도 측정용 서빙. serve_vllm.sh(27B)와 같은 설정이다 (GPU 0,2, TP=2, 길이 4096, 동시 8, 메모리 0.90, LoRA 켬).
# 다른 점: 모델(Qwen/Qwen3-14B-FP8)과 이름(Qwen3-14B)만 다르다. 14B는 텍스트 전용 모델이라 --language-model-only, --mm-processor-cache-gb를 뺐다.
source /var/tmp/csuhyeon/venvs/vllm/bin/activate
MODEL_ROOT=${MODEL_ROOT:-$HOME/var_tmp_backup_20261107}
export HF_HOME=$MODEL_ROOT/hf-fp8
export HF_HUB_OFFLINE=1
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0,2}
export VLLM_MQ_MAX_CHUNK_BYTES_MB=${VLLM_MQ_MAX_CHUNK_BYTES_MB:-1}
exec vllm serve Qwen/Qwen3-14B-FP8 \
  --revision 9a283b4a5efbc09ce247e0ae5b02b744739e525a \
  --served-model-name Qwen3-14B \
  --tensor-parallel-size 2 \
  --max-model-len 4096 \
  --max-num-seqs 8 \
  --gpu-memory-utilization 0.90 \
  --reasoning-parser qwen3 \
  --enable-lora --max-lora-rank 16 \
  --port 8001 "$@"
