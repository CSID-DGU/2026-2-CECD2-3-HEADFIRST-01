# Qwen3.8-27B QLoRA 학습

민원 접수 NLU용으로 Qwen3.8-27B를 QLoRA로 파인튜닝한다.
모델 원본을 4bit로 압축해 GPU 한 장(24GB)에 올리고, LoRA 어댑터만 학습한다.
GPU가 여러 장이면 장마다 모델을 하나씩 올리고 데이터를 나눠 학습한다(DDP).

| 파일 | 하는 일 |
|---|---|
| `train_qlora.py` | 학습 스크립트. 데이터 읽기 → 4bit 모델 + LoRA → 학습 → 어댑터 저장 → 검증 |
| `setup_local_venv.sh` | 학습용 가상환경을 로컬 디스크에 설치한다 |
| `requirements-torch-cu128.txt` | 1단계 설치 목록. PyTorch(CUDA 12.8 빌드)와 CUDA 라이브러리 |
| `requirements-libs.txt` | 2단계 설치 목록. transformers, peft, trl, bitsandbytes 등 |
| `../.env.example` | 경로 설정 견본. 복사해서 `AI/.env`를 만든다 |

검증한 환경: farm7 컨테이너, RTX A5000 24GB × 3, 드라이버 580, 시스템 CUDA 12.8, Python 3.12.15.

## 처음 한 번 준비

1. 경로 설정 파일을 만든다. 세 항목 모두 자기 환경의 절대 경로를 적는다.

   ```bash
   cp AI/.env.example AI/.env
   vi AI/.env        # HF_HOME, LOCAL_ROOT, RUNS_ARCHIVE
   ```

2. uv가 없으면 설치한다.

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. 학습 환경을 설치한다. 로컬 디스크 기준 10분 안팎(대부분 causal-conv1d 컴파일).

   ```bash
   bash AI/train/setup_local_venv.sh
   ```

4. 모델 원본을 내려받는다(약 55GB, `HF_HOME` 아래에 저장).

   ```bash
   source <LOCAL_ROOT>/venvs/qwen/bin/activate
   hf download Qwen/Qwen3.8-27B
   ```

## 학습 실행

학습은 몇 시간 걸리므로 터미널 연결이 끊겨도 계속 돌도록 `setsid nohup`으로 띄운다.

```bash
source <LOCAL_ROOT>/venvs/qwen/bin/activate
cd <레포 위치>

# GPU 3장
HF_HUB_OFFLINE=1 setsid nohup accelerate launch --num_processes 3 AI/train/train_qlora.py \
  --run_name 실험이름 --train 학습데이터.jsonl --valid 검증데이터.jsonl --archive \
  > <LOCAL_ROOT>/runs/실험이름.log 2>&1 < /dev/null &

# 진행 확인
tail -5 <LOCAL_ROOT>/runs/실험이름.log
```

- 데이터를 지정하지 않으면 `AI/data/sft_train.jsonl`, `AI/data/sft_valid.jsonl`을 쓴다.
- 짧게 시험만 할 때: `--max_train 48 --max_valid 8 --max_steps 6 --grad_accum 2 --eval_every 6`
- 학습 후 답을 직접 생성해 보려면 `--sample_generate 3`
- 기본 설정: 3 에포크, 학습률 2e-4, 장당 배치 1 × 누적 4, LoRA r=16 / alpha=32, 최대 1024토큰.
  나머지 옵션은 `python AI/train/train_qlora.py --help`

## 결과

- 학습 중 결과와 중간 저장본: `<LOCAL_ROOT>/runs/실험이름/`
- `--archive`를 주면 최종 어댑터(약 220MB)를 `<RUNS_ARCHIVE>/실험이름/`으로 복사한다.
- 모델 원본은 저장하지 않는다. 어댑터는 원본 Qwen3.8-27B 위에 얹어서 쓴다.

## 데이터 형식

한 줄에 한 건인 jsonl. 각 건은 `messages` 목록을 가지고, 마지막 메시지가 정답(assistant)이어야 한다.

```json
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."},
              {"role": "assistant", "content": "{\"active_intent\": ...}"}], "pattern": "NM-L1-3"}
```

형식이 바뀌면 `train_qlora.py`의 `load_jsonl` 함수만 고친다.

## 꼭 지킬 것

- **서비스할 때 thinking을 끈다.** 학습은 Qwen 대화 템플릿에 `enable_thinking=False`를 적용한 형식으로 한다.
  vLLM으로 서빙할 때도 같은 설정(`chat_template_kwargs={"enable_thinking": false}`)으로 호출해야 학습 효과가 난다.
- **가상환경과 캐시는 로컬 디스크에 둔다.** farm의 홈(NAS)은 작은 파일 쓰기가 매우 느리다.
  NAS에 설치했을 때 PyTorch 설치에 57분, 로컬에서는 4초가 걸렸다.
- **컨테이너 루트에 큰 파일을 두지 않는다.** ephemeral-storage 50Gi를 넘기면 Pod가 강제 종료된다.
  모델 원본(55GB)은 반드시 `HF_HOME`(홈/NAS 아래)에 둔다.
- **Pod가 재시작되면 로컬 디스크가 지워질 수 있다.** 가상환경이 없어졌으면 `setup_local_venv.sh`를 다시 실행한다.

## 실측값 (2026-10-19, 초안 데이터)

| 항목 | GPU 1장 | GPU 3장 |
|---|---|---|
| 모델 + LoRA 적재 후 메모리 (장당) | 16.9 GiB | 16.9 GiB |
| 학습 중 최대 메모리 (장당) | 18.2 GiB | 19.5 GiB |
| 스텝당 시간 (배치 1, 누적 2) | 약 5초 / 2건 | 약 5.1초 / 6건 |

데이터 4,750건 기준 1 에포크 약 396스텝, 약 1시간으로 예상한다.
