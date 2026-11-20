# 노인 실발화 라벨 (공개용, 313턴)

유튜브에 공개된 방송 · 라디오에서 노인 발화를 전사하고 사람이 듣고 라벨을 확정한 데이터다.
발화 원문은 재배포하지 않는다. 영상 URL과 시작 시각(초), 라벨만 담았다. URL의 해당 시점을 들으면 발화를 확인할 수 있다.

## 컬럼

| 컬럼 | 뜻 |
|---|---|
| dialogue_id | 턴 id |
| split | train / val / test (영상 단위 분할) |
| url, start_sec | 영상 주소와 발화 시작 시각 |
| call_date | 기준일(방송일) |
| slot | 질문받은 슬롯 (name / birth_date / occurred_date) |
| act | INFORM(값을 말함) / UNCERTAIN(재질문 대상) |
| canonical_value | INFORM일 때의 정답 값 |
| pattern | 발화 패턴 태그 |

## 건수 (action 단위)

| split | slot | act | 건수 |
|---|---|---|---:|
| test | birth_date | UNCERTAIN | 35 |
| test | name | INFORM | 20 |
| test | name | UNCERTAIN | 3 |
| test | occurred_date | UNCERTAIN | 4 |
| train | birth_date | INFORM | 1 |
| train | birth_date | UNCERTAIN | 104 |
| train | name | INFORM | 59 |
| train | name | UNCERTAIN | 11 |
| train | occurred_date | INFORM | 1 |
| train | occurred_date | UNCERTAIN | 13 |
| val | birth_date | UNCERTAIN | 35 |
| val | name | INFORM | 20 |
| val | name | UNCERTAIN | 3 |
| val | occurred_date | UNCERTAIN | 4 |
