from datetime import date

from ontology import load_questions
from session import Session, SessionDone, next_slot

# 대화 첫 질문 앞에 붙는 인사말
GREETING = "안녕하세요 구청 민원 접수입니다."

# 분류기 학습 데이터(AI/data/sft_train.jsonl)의 system 메시지와 글자 하나까지 같아야 한다.
# {today} 자리에 오늘 날짜(YYYY-MM-DD)가 들어간다
SYSTEM_PROMPT = """너는 구청 민원 전화 접수 상담에서 민원인 발화를 해석하는 NLU 모듈이다.
대화 이력과 마지막 USER 발화를 보고 JSON 한 개만 출력한다.

출력 형식: {"active_intent": "FileComplaint", "actions": [{"act": ..., "slot": ..., "values": [...], "canonical_values": [...]}]}

행위
- INFORM: 슬롯 값을 하나로 확정할 수 있을 때. values는 발화 표현, canonical_values는 아래 형식의 정규화 값 하나
- UNCERTAIN: 대답은 했지만 값을 하나로 확정할 수 없을 때. slot은 질문받은 슬롯, values와 canonical_values는 빈 배열
  - 해당: 번호 일부만 말함 / 생년월일에서 월 · 일 없이 연도 · 띠 · 나이만 말함 / 기억이 안 남 / 두 선택지에 걸침
  - 연도(또는 나이)와 월 · 일을 모두 말했으면 계산이 필요해도 INFORM (예: "올해 일흔이고 생일은 삼월 오일", 음력 날짜)

슬롯과 정규화
- consent: 개인정보 수집 동의. "true" 또는 "false"
- name: 성명 전체를 한글로 (예: 홍길동). 철자를 설명하면 설명된 음절만 이어 붙임
- birth_date: YYYY-MM-DD. 음력이면 뒤에 " (음력)". 나이는 한국식 세는나이로 계산
- phone: 010-XXXX-XXXX. 앞자리 010을 생략하면 010으로 채움. 여러 턴에 나눠 부르면 이력과 이어 붙임
- complaint_type: 불법 주정차 / 도로·보도 파손 / 가로등·보안등 고장 / 불법 광고물 / 쓰레기·동물 사체 / 기타 중 하나
- occurred_date: 일이 시작된 날 YYYY-MM-DD. 오늘 날짜 기준으로 계산
- reply_channel: 문자 / 전화 / 회신 안 함 중 하나

규칙
- 오늘 날짜: {today}
- 한 발화 안에서 고쳐 말하면 마지막 값으로 INFORM
- 상담원이 복창한 값을 고쳐 말하면 이력의 값에 교정을 적용한 최종 값으로 INFORM
- 질문받지 않은 슬롯까지 말하면 말한 슬롯마다 INFORM
- 마지막 USER 발화에 나온 정보만 출력. 이력에서 이미 받은 슬롯은 다시 출력하지 않음
- 설명 없이 JSON 한 개만 출력"""


def build_history(session: Session) -> list[str]:
    """세션 턴 기록을 대화 이력 줄로 만든다. 마지막 줄은 지금 묻고 있는 질문이다."""
    questions = load_questions()
    current_slot = next_slot(session)
    if current_slot is None:
        raise SessionDone(session.id)

    # 지금까지 물어본 슬롯 순서대로 질문(SYSTEM)과 답(USER)을 번갈아 적는다
    lines = []
    for turn in session.turns:
        lines.append(f"SYSTEM: {questions[turn.requested_slot]}")
        lines.append(f"USER: {turn.transcript}")
    lines.append(f"SYSTEM: {questions[current_slot]}")

    # 첫 질문 앞에 인사말을 붙인다
    lines[0] = f"SYSTEM: {GREETING} {lines[0].removeprefix('SYSTEM: ')}"
    return lines


def build_messages(session: Session, text: str, today: date) -> list[dict]:
    """분류기에 보낼 메시지(system, user)를 학습 데이터와 같은 형식으로 만든다."""
    history = "\n".join(build_history(session))
    user = f"[대화 이력]\n{history}\n\n[마지막 USER 발화]\n{text}"
    return [
        {"role": "system", "content": SYSTEM_PROMPT.replace("{today}", today.isoformat())},
        {"role": "user", "content": user},
    ]
