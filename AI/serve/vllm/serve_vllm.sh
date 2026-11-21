#!/bin/bash
# vLLM 시험 서빙: fp8 모델 + LoRA 어댑터, A5000 2장(TP=2). GPU 1은 다른 프로세스가 쓰고 있어 0,2를 쓴다.
source /var/tmp/csuhyeon/venvs/vllm/bin/activate
# 2026-11-07: 모델·어댑터는 홈(NAS) 복사본을 읽는다 (로컬 디스크 절약). 로컬로 옮기면 MODEL_ROOT만 바꾸면 된다
MODEL_ROOT=${MODEL_ROOT:-$HOME/var_tmp_backup_20261107}
export HF_HOME=$MODEL_ROOT/hf-fp8
export HF_HUB_OFFLINE=1
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0,2}
# 이 Pod의 /dev/shm이 64MB뿐이라 프로세스 간 메시지 버퍼(기본 16MB×10=160MB)를 1MB×10=10MB로 줄인다
export VLLM_MQ_MAX_CHUNK_BYTES_MB=${VLLM_MQ_MAX_CHUNK_BYTES_MB:-1}
# 2026-11-18: 서버를 끄지 않고 어댑터를 추가한다 (POST /v1/load_lora_adapter). add_adapter.sh로 바꾼 -vl 폴더만 올린다
export VLLM_ALLOW_RUNTIME_LORA_UPDATING=True
exec vllm serve Qwen/Qwen3.8-27B-FP8 \
  --revision 017b9c7af6b5689d5dd426a76e0bc077eb5ca20a \
  --served-model-name Qwen3.8-27B \
  --tensor-parallel-size 2 \
  --max-model-len 4096 \
  --max-num-seqs 8 \
  --gpu-memory-utilization 0.90 \
  --language-model-only --mm-processor-cache-gb 0 \
  --reasoning-parser qwen3 \
  --enable-lora --max-lora-rank 16 \
  --lora-modules v3=$MODEL_ROOT/adapters/v3-ckpt792-vl v3raw=$MODEL_ROOT/adapters/v3-ckpt792 \
    Aprime=$MODEL_ROOT/adapters/v31-ckpt842-vl v32A=$MODEL_ROOT/adapters/v32A-ckpt1152-vl v32B=$MODEL_ROOT/adapters/v32B-ckpt1150-vl \
  --port 8001 "$@"
