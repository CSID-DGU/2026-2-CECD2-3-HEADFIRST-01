import json
import os
from datetime import date
from functools import cache

from openai import OpenAI

from ontology import load_questions
from session import Session, SessionDone, next_slot

# 분류기 모드: mock(서버를 부르지 않고 정해진 답) / vllm(실제 분류기 호출)
CLASSIFIER_MODE = os.getenv("CLASSIFIER_MODE", "mock")

# 분류기(vLLM) 서버 주소와 모델 이름. 서버 주소는 공개 레포에 올리지 않도록 .env로만 받는다
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL")
VLLM_MODEL = os.getenv("VLLM_MODEL", "Qwen3.8-27B")

# 학습 데이터 system 메시지의 "슬롯과 정규화"에 나오는 슬롯 (description은 없다)
SLOTS = ["consent", "name", "birth_date", "phone", "complaint_type", "occurred_date", "reply_channel"]

# 분류기 출력 형식. vLLM이 이 형식에 맞는 JSON만 만들도록 강제한다
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "active_intent": {"type": "string", "enum": ["FileComplaint"]},
        "actions": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "act": {"type": "string", "enum": ["INFORM", "UNCERTAIN"]},
                    "slot": {"type": "string", "enum": SLOTS},
                    "values": {"type": "array", "items": {"type": "string"}},
                    "canonical_values": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["act", "slot", "values", "canonical_values"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["active_intent", "actions"],
    "additionalProperties": False,
}

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


@cache
def get_client() -> OpenAI:
    """vLLM 서버에 연결하는 클라이언트. 처음 한 번만 만들고 이후에는 재사용한다."""
    if not VLLM_BASE_URL:
        raise RuntimeError("VLLM_BASE_URL 환경변수가 없습니다. backend/.env.example을 참고해 .env를 만드세요.")
    # vLLM은 API 키를 확인하지 않지만 openai 라이브러리가 값을 요구해서 아무 값이나 넣는다
    return OpenAI(base_url=VLLM_BASE_URL, api_key="EMPTY", timeout=60)


def call_vllm(messages: list[dict]) -> dict:
    """분류기에 메시지를 보내고, 출력 JSON을 dict로 돌려준다."""
    response = get_client().chat.completions.create(
        model=VLLM_MODEL,
        messages=messages,
        temperature=0,  # 같은 입력이면 같은 답이 나오도록 무작위성을 끈다
        max_tokens=300,
        response_format={"type": "json_schema", "json_schema": {"name": "nlu_output", "schema": OUTPUT_SCHEMA}},
        # Qwen3의 '생각하는 글' 모드를 끈다. 학습 데이터도 JSON만 바로 출력한다
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return json.loads(response.choices[0].message.content)


# consent 값은 분류기가 글자("true"/"false")로 내므로 참/거짓 값으로 바꾼다
CONSENT_VALUES = {"true": True, "false": False}


def to_frames(output: dict) -> list[dict]:
    """분류기 출력(학습 데이터 형식)을 세션 형식 [{slot, action, value}]로 바꾼다."""
    frames = []
    for action in output["actions"]:
        slot = action["slot"]
        act = action["act"].lower()  # INFORM → inform, UNCERTAIN → uncertain
        # 값은 canonical_values의 첫 번째. uncertain이거나 값이 없으면 None
        value = action["canonical_values"][0] if act == "inform" and action["canonical_values"] else None

        if slot == "consent" and act == "inform":
            if value not in CONSENT_VALUES:
                # "true"/"false"가 아닌 값은 동의 여부를 알 수 없으므로 uncertain으로 본다
                act, value = "uncertain", None
            else:
                value = CONSENT_VALUES[value]

        frames.append({"slot": slot, "action": act, "value": value})
    return frames


def mock_output(session: Session, text: str) -> dict:
    """분류기 대신 정해진 답을 만든다. 지금 묻는 슬롯에 발화를 그대로 값으로 넣는다.
    발화에 '몰라'나 '모르'가 있으면 UNCERTAIN을 낸다."""
    slot = next_slot(session)
    if "몰라" in text or "모르" in text:
        action = {"act": "UNCERTAIN", "slot": slot, "values": [], "canonical_values": []}
    else:
        value = "true" if slot == "consent" else text
        action = {"act": "INFORM", "slot": slot, "values": [value], "canonical_values": [value]}
    return {"active_intent": "FileComplaint", "actions": [action]}


def classify(session: Session, text: str, today: date | None = None) -> tuple[list[dict], dict]:
    """사용자 발화를 분류해 (세션 형식 frames, 분류기 원래 출력)을 돌려준다.
    today를 주지 않으면 오늘 날짜를 쓴다. 대화가 끝난 세션이면 SessionDone."""
    messages = build_messages(session, text, today or date.today())
    if CLASSIFIER_MODE == "mock":
        raw = mock_output(session, text)
    elif CLASSIFIER_MODE == "vllm":
        raw = call_vllm(messages)
    else:
        raise ValueError(f"알 수 없는 CLASSIFIER_MODE: {CLASSIFIER_MODE!r} (가능한 값: mock, vllm)")
    return to_frames(raw), raw
