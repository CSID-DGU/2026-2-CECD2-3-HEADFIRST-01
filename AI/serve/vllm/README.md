# vLLM 서빙 (farm7)

백엔드가 부르는 분류기 모델을 farm7 pod에서 vLLM으로 띄우는 스크립트. farm7에서 쓰는 파일(`~/capstone_design_2/envs/vllm/`, `/var/tmp/csuhyeon/`)을 그대로 복사한 것이라 경로가 farm7 기준으로 적혀 있다.

| 파일 | 하는 일 |
|---|---|
| `install_vllm.sh` | vLLM 가상환경을 `/var/tmp/csuhyeon/venvs/vllm`에 만든다 |
| `serve_vllm.sh` | 27B(Qwen3.8-27B, FP8, A5000 GPU 0·2번 tensor-parallel 2)와 LoRA 어댑터(Aprime, v32A, v32B 등)를 포트 8001에 띄운다 |
| `serve_vllm_14b.sh` | 14B(Qwen/Qwen3-14B-FP8)를 같은 GPU · 같은 포트에 띄운다. 어댑터는 `--lora-modules`로 넘긴다 |
| `vllm_ctl.sh` | `start` / `stop` / `status` — 27B 서버를 켜고 끄고 상태를 본다 |
| `add_adapter.sh` | H200에서 받아 온 어댑터를 `MODEL_ROOT/adapters/<이름>-vl`에 복사한다. Qwen3.8 어댑터만 키 이름을 바꾼다(model.layers. → model.language_model.layers.) |

GPU 2장에는 모델을 하나만 올릴 수 있다. 14B를 띄우려면 27B를 꺼야 하고, 그동안 백엔드가 멈춘다.
