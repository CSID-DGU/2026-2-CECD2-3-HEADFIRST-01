# 학습 전/후 평가

같은 시험지를 학습 전 모델과 학습 후 모델에게 풀게 하고, 멘토 서버 베이스라인과 같은 채점 기준으로 비교한다.

| 파일 | 하는 일 |
|---|---|
| `eval_local.py` | 4bit 모델(+어댑터)로 평가셋을 풀고 채점한다. 채점은 `check_responses.py` 원본을 불러다 쓴다 |
| `compare_runs.py` | 결과 파일 여러 개를 같은 문제끼리 모아 점수를 나란히 비교한다 |
| `run_track1_local.py` | 트랙 1(패턴 규칙 미적용 vs 적용, 실제 발화 232건)을 4bit 모델로 돌린다. 프롬프트 · 채점은 팀원의 `run_track1.py`를 그대로 쓴다 |
| `run_raw_eval_local.py` | 노인 실발화 70건을 학습 전 · 학습 후(어댑터) 연달아 잰다. 채점은 팀원의 `run_raw_eval.py`를 그대로 쓴다 |
| `run_raw_test_local.py` | 노인 raw test 62(트랙 1 본실험 시험지)를 학습 전 + 어댑터 여러 개로 풀고 팀원의 `evaluate_raw.py`로 채점한다 |

## 트랙 1 본실험: 원본 vs 패턴 데이터 학습 (노인, 2026-10-21)

조건 R = 노인 원본 `raw_노인_train.jsonl` 189, 조건 P = 패턴 합성 `sft_track1_pattern189.jsonl` 189 (셀 분포 · 건수 동일). valid는 둘 다 `raw_노인_val.jsonl` 62.
레시피는 v3-r16-e3와 같다(r16, lr 2e-4, 3 epoch, 한 번에 12건). R은 GPU 3장 × grad_accum 4, P는 GPU 0번이 NAS 대기에 묶여 GPU 2장 × grad_accum 6으로 돌렸다(한 번에 12건, 48스텝은 같음).
데이터는 서버 `~/capstone_design_2/data/raw_elderly_v1/`, `data/track1/` (git 제외). 노인 70 중 47문제가 R 학습 데이터에 들어 있으므로 R/P 비교에는 노인 70을 쓰지 않는다.

```bash
HF_HUB_OFFLINE=1 python AI/eval/run_raw_test_local.py --kit ~/capstone_design_2/data/raw_elderly_v1 --out_dir <결과폴더> \
  --adapter R_ep1=<R폴더>/checkpoint-16 --adapter P_ep1=<P폴더>/checkpoint-16
```

검증 손실: R 0.0182 / 0.0190 / 0.0193, P 0.0219 / 0.0238 / 0.0230 (epoch 1·2·3) → 둘 다 epoch 1(checkpoint-16)을 기준으로 쓴다.

| 모델 | raw test 62 macro-F1 | UNCERTAIN recall | JGA (20) | 실발화 227 (base 모드) |
|---|---|---|---|---|
| 학습 전 | 0.922 | 0.905 | 0.900 | 93.8 |
| R epoch 1 | **0.963** | 0.976 | 0.950 | 93.4 |
| P epoch 1 | 0.945 | 0.952 | 0.950 | **94.3** |
| (참고) R epoch 2 / 3 | 0.964 / 0.964 | 0.952 / 0.952 | 1.000 / 1.000 | - |
| (참고) P epoch 2 / 3 | 0.945 / 0.928 | 0.952 / 0.929 | 0.900 / 0.900 | - |

다수결 베이스라인(act 정확도) 0.952. 파싱 실패는 모든 조건 0.
R과 P의 raw test 차이는 1문제("팔월 삼일에 돼요." 정답 UNCERTAIN, P만 2024-08-03으로 지어냄), 실발화 227 차이는 2문제다. 모두 표본 오차 범위라 "R ≈ P"로 읽는다.

## 노인 실발화 70건

방송 · 유튜브 노인 자기소개 STT를 민원 대화에 옮긴 평가 전용 셋이다(`~/capstone_design_2/data/eval_real/eval_raw_elderly.jsonl`, 학습 금지).
70건 중 50건이 UNCERTAIN 정답이라, 값을 지어내지 않고 "판단 불가"를 고르는지를 주로 본다. 채점은 (행위, 슬롯, 값) 집합이 완전히 같아야 맞음이다. GPU 1장, 2회에 약 16분.

```bash
HF_HUB_OFFLINE=1 python AI/eval/run_raw_eval_local.py --kit ~/capstone_design_2/data/eval_real \
  --adapter <어댑터 폴더> --name <이름> --out_dir <LOCAL_ROOT>/runs/elderly/<이름>
```

| 날짜 | 모델 | 전체 (%) | 비고 |
|---|---|---|---|
| 2026-10-21 | 베이스 4bit, temperature 0 | 97.1 (68/70) | |
| 2026-10-21 | v3-r16-e3 epoch 1 (checkpoint-396) | 95.7 (67/70) | 개선 2 · 악화 3. 지어내기 2건은 epoch 1에서도 나옴("공사년생" → 1904-06-03, "민우 아빠" → 민우). "한 사 년 됐어요"는 epoch 1에선 UNCERTAIN(정답) |
| 2026-10-21 | v3-r16-e3 epoch 2 (checkpoint-792) | 94.3 (66/70) | 개선 2 · 악화 4. 악화 중 3건이 값 지어내기("공사년생" → 1904-06-02, "한 사 년 됐어요" → 2022-10-19, "민우 아빠" → 민우) |

이미 학습 전 결과가 있으면 `--skip_base`로 어댑터 쪽만 다시 잰다.

학습 데이터는 UNCERTAIN이 들어간 행이 5.3%(250/4,750)인데, 이 셋은 71.4%(50/70)다. 학습 후 모델이 INFORM 쪽으로 기운 원인 후보다. 70건이라 1건이 1.4점이어서, 차이는 아직 방향성으로만 본다.

## 트랙 1 v0 (실제 발화 232건)

같은 학습 전 모델에 system 프롬프트만 바꿔 비교한다. pattern 모드는 숫자 패턴 규칙 6개와 예시 4개를 덧붙인다.
트랙 1 키트(`run_track1.py`, `testset_v0.jsonl`)는 서버에서 `~/capstone_design_2/data/eval_real/`에 있다(git 제외). GPU 1장으로 5분 안쪽.

```bash
HF_HUB_OFFLINE=1 python AI/eval/run_track1_local.py --kit ~/capstone_design_2/data/eval_real --out_dir <LOCAL_ROOT>/runs/track1/<이름>
```

| 날짜 | 모델 | base | pattern | 비고 |
|---|---|---|---|---|
| 2026-10-21 | 베이스 4bit, temperature 0 | 91.8 (213/232) | 94.8 (220/232) | v0. 대조군(아라비아 40 · 혼합 40) 둘 다 100. 한글 152: 87.5 → 92.1. 다산콜 12: 둘 다 16.7 |
| 2026-10-21 | 베이스 4bit, temperature 0 | **93.8** (213/227) | **95.2** (216/227) | v0.1. 소상공인 한글 136: 96.3 → 99.3. 대조군 둘 다 100. 다산콜 11: 18.2 → 9.1 |
| 2026-10-21 | v3-r16-e3 epoch 2 (checkpoint-792) | 93.8 (213/227) | 93.0 (211/227) | v0.1. 파싱 실패 0(모든 답이 숫자 또는 "없음"). 어댑터 없음 대비 base +4/−4, pattern +3/−8. 악화는 대부분 계산해 버린 답("팔 기가 짜리 두개요" → 8, "49만원이야 20프로 하면" → 392000) |

v0 주의: 뒤집힌 9건(맞게 됨 8 / 틀리게 됨 1) 중 DS-008은 pattern 프롬프트의 예시 문장과 같은 문제다. SS-052 · SS-103 · SS-132 · SS-133은 정답 라벨이 애매하다(예: "한 통에 몇 개 들었어요?" → 정답 1).
다산콜은 숫자가 가려졌거나(`*층`, `**분`) 전사에서 사라진 문제가 많다. 팀 검수 전까지는 방향성 확인용으로만 본다.

v0.1(팀원 수정본, `run_track1_v01.py` · `testset_v0_1.jsonl`)은 위 애매한 4문제와 DS-005("몇 백 미터")를 빼고, pattern 프롬프트 예시를 시험 문제와 겹치지 않는 문장으로 바꿨다. base 모드 답은 v0와 227문제 모두 같다(프롬프트가 같으므로).
뒤집힌 5건: 맞게 됨 4(SS-017 34580→4580, SS-033 1200→2200, SS-110 128000→28000, SS-138 2500→22500, 모두 한글 가격) / 틀리게 됨 1(DS-006, `*층` 가려진 문제). 예시가 바뀐 뒤에도 SS-033 · SS-110 · SS-138은 그대로 맞았다.

```bash
HF_HUB_OFFLINE=1 python AI/eval/run_track1_local.py --kit ~/capstone_design_2/data/eval_real \
  --script run_track1_v01 --data testset_v0_1.jsonl --out_dir <LOCAL_ROOT>/runs/track1/<이름>
```

## 원칙

- **바뀌는 건 어댑터 하나뿐이다.** 학습 전과 후 모두 같은 서버, 같은 4bit(NF4) 모델, 같은 프롬프트, 같은 채점 코드로 잰다.
- **채점 코드는 고치지 않는다.** `check_responses.py`(멘토 서버 베이스라인을 낸 원본)의 문제 만들기 · 프롬프트 · JSON 읽기 · 채점 · 집계를 그대로 쓴다. 원본은 vLLM 서버에 HTTP로 묻는데, `eval_local.py`는 이 부분만 GPU의 모델에 직접 묻도록 바꿨다.
- **주 측정은 temperature 0이다.** 항상 확률 1등 답만 골라서 다시 돌려도 같은 답이 나오고, 실제 서비스 조건과 같다. 그래서 1회만 잰다.
- **temperature 0.7은 확인용으로 학습 전에 1회만 잰다.** 멘토 서버 설정(0.7, top_p 0.8, top_k 20)과 같은 조건으로 재서, 우리 환경의 점수가 멘토 결과(62.1)와 비슷한지만 본다.
- **JGA 분모에서 state가 None인 문제는 뺀다.** 정답에 INFORM이 없는 문제(UNCERTAIN 등)는 JGA를 계산할 수 없어서다. 기존 수치(56.8, 62.1)도 같은 방식이다.

## 시험지와 채점 키트

팀원에게 받은 데이터로, git에 올리지 않는다. 서버에서는 `~/capstone_design_2/data/eval_mini/`에 있다.

| 파일 | 내용 |
|---|---|
| `minwon_eval_mini155.json` | 기존 패턴 31종 × 5 = 155문제. 동결 평가셋 620에서 뽑았다 |
| `minwon_eval_v3add_mini20.json` | v3 신규 패턴 4종 × 5 = 20문제 |
| `check_responses.py` | 멘토 서버 베이스라인을 낸 채점 스크립트 원본 |
| `results_mentor_ref_mini155.jsonl` | 멘토 서버 결과 중 mini155에 해당하는 150행. DS-7 5건은 없다(측정 후 평가셋에 추가됨). JGA 62.1 (140문제 기준) |

시험지 문제의 노이즈 발화는 학습셋과 겹치는 것이 0건이다(팀원 확인).

## 실행

학습 스크립트와 같은 가상환경과 `AI/.env`를 쓴다. GPU 3장이면 문제를 3등분해 나눠 푼다.
175문제 기준 모델 로딩 포함 약 10분 걸린다(문제당 약 7초).

```bash
source <LOCAL_ROOT>/venvs/qwen/bin/activate
cd <레포 위치>
KIT=~/capstone_design_2/data/eval_mini
OUT=<LOCAL_ROOT>/runs/eval
mkdir -p $OUT

# 1) 학습 전 · 주 측정 (temperature 0, 175문제)
HF_HUB_OFFLINE=1 setsid nohup accelerate launch --num_processes 3 AI/eval/eval_local.py \
  --kit $KIT --data $KIT/minwon_eval_mini155.json $KIT/minwon_eval_v3add_mini20.json \
  --out $OUT/base_t0.jsonl > $OUT/base_t0.log 2>&1 < /dev/null &

# 2) 학습 전 · 확인용 (temperature 0.7, mini155만)
HF_HUB_OFFLINE=1 setsid nohup accelerate launch --num_processes 3 AI/eval/eval_local.py \
  --kit $KIT --data $KIT/minwon_eval_mini155.json --temperature 0.7 \
  --out $OUT/base_t07.jsonl > $OUT/base_t07.log 2>&1 < /dev/null &

# 3) 학습 후 · 주 측정 (1과 같은 명령에 --adapter만 추가)
HF_HUB_OFFLINE=1 setsid nohup accelerate launch --num_processes 3 AI/eval/eval_local.py \
  --kit $KIT --data $KIT/minwon_eval_mini155.json $KIT/minwon_eval_v3add_mini20.json \
  --adapter <어댑터 폴더> --out $OUT/<실험이름>_t0.jsonl > $OUT/<실험이름>_t0.log 2>&1 < /dev/null &

# 진행 확인 (GPU 0번이 맡은 문제 기준)
tail -3 $OUT/base_t0.log
```

1과 2는 GPU를 같이 쓰므로 하나가 끝난 뒤 다음 것을 띄운다.
시험 삼아 몇 문제만 풀어 보려면 `python AI/eval/eval_local.py ... --limit 5`처럼 GPU 1장으로 돌린다.

끝나면 로그 끝에 전체 · 대분류별 · 패턴별 표가 찍히고, 문제별 결과(모델 답 `raw`, 읽어낸 JSON `pred`, 채점 `score`)가 `--out` 파일에 남는다. 형식은 `check_responses.py` 결과 파일과 같다.

## 비교

```bash
# 학습 전 vs 학습 후 (패턴별 JGA까지)
python AI/eval/compare_runs.py --kit $KIT --by-pattern $OUT/base_t0.jsonl $OUT/<실험이름>_t0.jsonl

# 우리 환경 확인: 멘토 서버 결과 vs 우리 0.7 측정 (공통 150문제, JGA는 140문제)
python AI/eval/compare_runs.py --kit $KIT $KIT/results_mentor_ref_mini155.jsonl $OUT/base_t07.jsonl
```

`compare_runs.py`는 모든 파일에 공통으로 있는 문제만 골라 비교하고, 원본 `score`로 다시 채점한다.
예전 결과 파일에는 slot_F1 계산용 항목이 없어서다. 맞음/틀림 판정은 저장된 값과 같다.

## 결과 기록

| 날짜 | 모델 | temperature | 시험지 | JGA | 비고 |
|---|---|---|---|---|---|
| (멘토 서버) | 베이스, vLLM | 0.7 | mini155 중 150 | 62.1 (140) | 참조치 |
| 2026-10-20 | 베이스 4bit, 어댑터 없음 | 0 | mini155+mini20 (175) | **64.4** (160) | 주 측정. mini155만 61.4 (145), mini20만 93.3 (15) |
| 2026-10-20 | 베이스 4bit, 어댑터 없음 | 0.7 | mini155 (155) | 62.1 (145) | 확인용 |
| 2026-10-21 | v3-r16-e3 epoch 1 (checkpoint-396) | 0 | mini155+mini20 (175) | 96.2 (160) | |
| 2026-10-21 | v3-r16-e3 epoch 2 (checkpoint-792) | 0 | mini155+mini20 (175) | **98.8** (160) | 오답 2건: DA-4 "그저께" 날짜 하루 차이, NM-L1-3 받침 누락(이진우→이지우) |
| 2026-10-21 | v3-r16-e3 epoch 3 (checkpoint-1188) | 0 | mini155+mini20 (175) | 98.8 (160) | epoch 2와 오답까지 같음 |
| 2026-10-21 | 베이스 4bit, 어댑터 없음 | 0 | v3add 80 | 85.0 (60) | DA-6 20문제는 정답 state가 None이라 JGA에서 빠짐 |
| 2026-10-21 | v3-r16-e3 epoch 2 (checkpoint-792) | 0 | v3add 80 | **98.3** (60) | 오른 곳은 거의 NM-L2-4 (55→95) |
| 2026-10-21 | 베이스 4bit, 어댑터 없음 | 0 | 동결 평가셋 620 (minwon_eval_v2.json) | 57.4 (580) | 31패턴 × 20. 행위 F1 98.0 |
| 2026-10-21 | v3-r16-e3 epoch 2 (checkpoint-792) | 0 | 동결 평가셋 620 | **98.3** (580) | 발표용 수치. 유일하게 내려간 패턴 DA-4 100→85, 아직 100이 아닌 곳 DA-5 90 · NM-SP-1 85 · DA-1 95 · NM-L1-3 95 |

JGA 괄호 안은 분모(state가 None이 아닌 문제 수). 멘토 결과와 공통 150문제로 맞추면 멘토 62.1 / 우리 0.7 60.7 / 우리 0 60.0 (모두 140문제 기준)으로, 우리 환경(4bit, transformers)이 멘토 서버와 크게 다르지 않다.
학습 전 패턴별로는 NM-L1-2 · NM-L2-1이 0%, DA-2 · NM-L2-2 · NM-L2-3 · NU-3 · NU-5가 20%로 가장 약하다(패턴당 5문제라 한 문제가 20점).

주의: 미니 평가셋은 학습 데이터와 같은 생성기로 만들어져 문장 틀과 노이즈 방식이 같다(채점 발화가 글자까지 같은 경우는 0건).
학습 후 98.8은 "같은 분포의 문제" 점수이고, 실제 사람 발화에 대한 성능은 실발화 232 · 노인 70 평가로 따로 확인해야 한다.
