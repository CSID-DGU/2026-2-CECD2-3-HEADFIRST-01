# H200 학습 실행 (nvl03, 공유 계정 iot3)

H200 서버에서 `train_qlora.py`를 돌린 실행 스크립트. H200에서는 `~/dgustu/code/AI/train/` 아래에 두고 쓴다. 학습 데이터는 저장소에 없고 H200의 `~/dgustu/data/v32/`에만 있다.

| 파일 | 하는 일 |
|---|---|
| `check_h200.sh` | v3.2 학습 전에 H200 환경을 점검한다 (읽기만 함, 끝에 [OK] / [확인 필요] 목록) |
| `run_v32.sh` | 27B를 v3.2 실험 A · B 데이터로 학습한다 (4bit QLoRA, r 16, alpha 32, 3에폭, GPU 0번 1장) |
| `pack_v32.sh` | 27B 실험 A · B의 에폭 2 어댑터를 farm7로 보낼 파일로 묶는다 |
| `run_q14.sh` | 14B(Qwen/Qwen3-14B)를 같은 데이터 · 같은 설정으로 학습한다. 바뀐 것은 `--model`뿐이다 |
| `pack_q14.sh` | 14B 실험 A · B의 에폭 2 어댑터를 `q14_adapters.tar`로 묶는다 |
