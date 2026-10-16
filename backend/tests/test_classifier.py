import json
from datetime import date
from pathlib import Path

import pytest

from classifier import build_history, build_messages
from session import SessionDone, add_turn, create_session, next_slot

# 분류기 학습 데이터 (레포 최상위의 AI/data/sft_train.jsonl)
SFT_PATH = Path(__file__).resolve().parents[2] / "AI" / "data" / "sft_train.jsonl"


def load_example(dialogue_id):
    """학습 데이터에서 dialogue_id가 같은 예시의 messages를 찾아 돌려준다."""
    with open(SFT_PATH, encoding="utf-8") as f:
        for line in f:
            example = json.loads(line)
            if example["dialogue_id"] == dialogue_id:
                return example["messages"]
    raise KeyError(dialogue_id)


def answer(session, transcript, slot, value):
    """사용자가 지금 묻는 슬롯에 답한 턴을 추가한다."""
    add_turn(session, transcript, [{"slot": slot, "action": "inform", "value": value}])


def test_첫_질문에는_인사말이_붙는다():
    session = create_session()
    assert build_history(session) == [
        "SYSTEM: 안녕하세요 구청 민원 접수입니다. 민원 접수를 위해 개인정보 수집에 동의하시나요?"
    ]


def test_값을_못_받은_턴도_이력에_남는다():
    session = create_session()
    answer(session, "네", "consent", True)
    add_turn(session, "이름은 왜요", [{"slot": "name", "action": "uncertain", "value": None}])
    assert build_history(session)[-2:] == [
        "USER: 이름은 왜요",
        "SYSTEM: 생년월일을 말씀해 주시겠어요?",
    ]


def test_대화가_끝났으면_SessionDone():
    session = create_session()
    while (slot := next_slot(session)) is not None:
        add_turn(session, "몰라요", [{"slot": slot, "action": "uncertain", "value": None}])
    with pytest.raises(SessionDone):
        build_history(session)


def test_학습_데이터와_같은_프롬프트_이름_질문():
    # 동의 다음 이름을 묻는 중에 철자를 풀어 말한 예시
    session = create_session()
    answer(session, "네 동의합니다.", "consent", True)

    messages = build_messages(
        session,
        "지읒에 어 니은 받침 그다음 정원 할 때 정 그다음 니은에 아 미음 받침",
        date(2026, 11, 21),
    )
    assert messages == load_example("NM-L1-3_0147")[:2]


def test_학습_데이터와_같은_프롬프트_민원_유형_질문():
    # 네 슬롯을 받은 뒤 민원 유형을 묻는 예시
    session = create_session()
    answer(session, "네 동의합니다.", "consent", True)
    answer(session, "문재민이요.", "name", "문재민")
    answer(session, "1944년 6월 24일이요.", "birth_date", "1944-06-24")
    answer(session, "010-1719-3085요.", "phone", "010-1719-3085")

    messages = build_messages(session, "배수구 덮개가 빠져서 발이 빠질 뻔했어", date(2026, 11, 19))
    assert messages == load_example("CT-1_0039")[:2]
