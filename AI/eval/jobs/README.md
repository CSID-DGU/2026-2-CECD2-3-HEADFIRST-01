# 평가 · 응답 속도 측정 실행 순서 (farm7)

`AI/eval/`의 평가 스크립트를 어떤 순서로 돌렸는지 적은 실행 스크립트. farm7의 `~/capstone_design_2/envs/vllm/`에서 복사했고, 경로가 farm7 기준이다. 시험지(하드셋, raw test 62 등)와 결과는 저장소에 없고 farm7에만 있다.

| 파일 | 하는 일 |
|---|---|
| `eval_aprime_20261118.sh` | A′(v3.1, checkpoint-842)를 vLLM에 올리고 하드 dev · test, raw test 62, 실발화 227, 생성 620으로 평가한다 (vLLM 재시작, 그동안 백엔드 멈춤) |
| `eval_nf4_20261118.sh` | 학습 전 27B와 A′를 transformers + nf4(4bit)로 하드 dev · test에서 평가한다. GPU 3장을 쓰려고 vLLM을 잠시 끈다 |
| `eval_v32_20261119.sh` | 27B v3.2 실험 A · B 어댑터를 서버를 켠 채로 올리고 평가한다 (하드 dev · test, raw test 62, 실발화 227, 생성 620) |
| `eval_q14_20261119.sh` | 27B를 끄고 14B를 띄워 학습 전 14B와 14B 실험 A · B 어댑터를 평가하고 응답 속도를 잰다. 끝나면 27B를 다시 켠다 |
| `eval_seeds_20261120.sh` | seed 43 · 44로 다시 학습한 어댑터를 평가한다 (vLLM은 끄지 않음) |
| `latency_14b_20261119.sh` | 학습 전 14B의 응답 속도를 잰다 |
| `latency_27b_adapters_20261121.sh` | 27B v32A · v32B 어댑터의 응답 속도를 검증셋으로 잰다 |
| `latency_hardtest_20261121.sh` | 27B · 14B 어댑터 4개의 응답 속도를 하드 test 200문제 × 3회로 잰다 (작업 5 최종 숫자) |

응답 속도 결과는 `AI/eval/results/latency/`에 있다 (`summary.json`: 시간과 토큰 수만 있고 문제 내용은 없다).
