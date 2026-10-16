import json
from datetime import date
from pathlib import Path

import pytest

import classifier
from classifier import build_history, build_messages, classify, to_frames
from session import SessionDone, add_turn, create_session, next_slot

# 분류기 학습 데이터 (레포 최상위의 AI/data/sft_train.jsonl)
SFT_PATH = Path(__file__).resolve().parents[2] / "AI" / "data" / "sft_train.jsonl"


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    """테스트는 환경변수와 상관없이 mock 모드로 돌려 실제 서버를 부르지 않는다."""
    monkeypatch.setattr(classifier, "CLASSIFIER_MODE", "mock")


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


def output(*actions):
    """분류기 출력 형식을 만든다. actions: (act, slot, canonical_values) 튜플들."""
    return {
        "active_intent": "FileComplaint",
        "actions": [
            {"act": act, "slot": slot, "values": values, "canonical_values": values}
            for act, slot, values in actions
        ],
    }


def test_INFORM은_소문자로_바꾸고_첫_번째_값을_꺼낸다():
    assert to_frames(output(("INFORM", "name", ["전정남"]))) == [
        {"slot": "name", "action": "inform", "value": "전정남"}
    ]


def test_UNCERTAIN은_값이_None():
    assert to_frames(output(("UNCERTAIN", "phone", []))) == [
        {"slot": "phone", "action": "uncertain", "value": None}
    ]


def test_슬롯_여러_개를_모두_바꾼다():
    frames = to_frames(output(("INFORM", "name", ["성미경"]), ("INFORM", "birth_date", ["1949-03-04"])))
    assert [frame["slot"] for frame in frames] == ["name", "birth_date"]


def test_consent는_참_거짓_값으로_바꾼다():
    assert to_frames(output(("INFORM", "consent", ["true"])))[0]["value"] is True
    assert to_frames(output(("INFORM", "consent", ["false"])))[0]["value"] is False


def test_consent가_true_false가_아니면_uncertain():
    assert to_frames(output(("INFORM", "consent", ["네"]))) == [
        {"slot": "consent", "action": "uncertain", "value": None}
    ]


def test_mock은_지금_묻는_슬롯에_발화를_넣는다():
    session = create_session()
    answer(session, "네", "consent", True)
    frames, raw = classify(session, "김천일이요")
    assert frames == [{"slot": "name", "action": "inform", "value": "김천일이요"}]
    assert raw["actions"][0]["act"] == "INFORM"


def test_mock_동의_질문에는_True():
    frames, _ = classify(create_session(), "네 동의합니다")
    assert frames == [{"slot": "consent", "action": "inform", "value": True}]


def test_mock_몰라가_있으면_uncertain():
    session = create_session()
    answer(session, "네", "consent", True)
    frames, _ = classify(session, "이름이 생각이 안 나 몰라")
    assert frames == [{"slot": "name", "action": "uncertain", "value": None}]


def test_vllm_모드는_학습_데이터_형식_메시지로_호출한다(monkeypatch):
    sent = []

    def fake_call_vllm(messages):
        sent.append(messages)
        return output(("INFORM", "consent", ["true"]))

    monkeypatch.setattr(classifier, "CLASSIFIER_MODE", "vllm")
    monkeypatch.setattr(classifier, "call_vllm", fake_call_vllm)
    session = create_session()
    frames, _ = classify(session, "네 동의합니다", date(2026, 11, 21))

    assert sent == [build_messages(session, "네 동의합니다", date(2026, 11, 21))]
    assert frames == [{"slot": "consent", "action": "inform", "value": True}]


def test_알_수_없는_모드는_에러(monkeypatch):
    monkeypatch.setattr(classifier, "CLASSIFIER_MODE", "gpt")
    with pytest.raises(ValueError):
        classify(create_session(), "네")
