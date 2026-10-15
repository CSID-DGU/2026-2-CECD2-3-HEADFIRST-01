from datetime import timedelta

import pytest

from session import (
    SessionDone,
    SessionNotFound,
    add_turn,
    create_session,
    get_session,
    merge_value,
    next_slot,
)


def inform(slot, value):
    return {"slot": slot, "action": "inform", "value": value}


def uncertain(slot):
    return {"slot": slot, "action": "uncertain", "value": None}


def test_새_세션은_모든_슬롯이_비어있고_첫_질문은_consent():
    session = create_session()
    assert all(value is None for value in session.slot_values.values())
    assert next_slot(session) == "consent"


def test_세션_ID_형식():
    date, time, rand = create_session().id.split("-")
    assert len(date) == 6 and len(time) == 6 and len(rand) == 6


def test_없는_세션은_SessionNotFound():
    with pytest.raises(SessionNotFound):
        get_session("0000-000000-000000")


def test_30분_지난_세션은_SessionNotFound():
    session = create_session()
    session.last_used -= timedelta(minutes=31)
    with pytest.raises(SessionNotFound):
        get_session(session.id)


def test_inform은_저장하고_uncertain은_그대로():
    session = create_session()
    add_turn(session, "네 동의해요", [inform("consent", True)])
    add_turn(session, "이름은 왜요", [uncertain("name")])
    assert session.slot_values["consent"] is True
    assert session.slot_values["name"] is None


def test_동의_안함_false도_완료로_본다():
    session = create_session()
    add_turn(session, "동의 안 할래요", [inform("consent", False)])
    assert session.slot_values["consent"] is False
    assert next_slot(session) == "name"


def test_한_발화의_여러_슬롯을_모두_반영하고_완료된_슬롯은_건너뛴다():
    session = create_session()
    add_turn(session, "네", [inform("consent", True)])
    add_turn(
        session,
        "김천일이고 오공년생 칠월 이일이에요",
        [inform("name", "김천일"), inform("birth_date", "1950-07-02")],
    )
    assert session.slot_values["birth_date"] == "1950-07-02"
    assert next_slot(session) == "phone"


def test_물어본_슬롯은_값이_비어도_다시_묻지_않는다():
    session = create_session()
    add_turn(session, "네", [inform("consent", True)])
    add_turn(session, "내 이름이 뭐였더라", [uncertain("name")])
    assert next_slot(session) == "birth_date"


def test_물음표가_있으면_아직_안_물은_슬롯은_묻는다():
    session = create_session()
    add_turn(session, "네", [inform("consent", True)])
    add_turn(session, "오공년생이요", [uncertain("name"), inform("birth_date", "1950-??-??")])
    assert next_slot(session) == "birth_date"


def test_같은_슬롯_새_값은_덮어쓴다():
    session = create_session()
    add_turn(session, "네", [inform("consent", True)])
    add_turn(session, "김천일", [inform("name", "김천일")])
    add_turn(session, "아 이름은 김천이요", [uncertain("birth_date"), inform("name", "김천이")])
    assert session.slot_values["name"] == "김천이"


def test_물음표_자리만_채운다():
    assert merge_value("010-????-7777", "010-1234-????") == "010-1234-7777"
    assert merge_value("1950-??-??", "1950-07-02") == "1950-07-02"
    assert merge_value(None, "1950-??-??") == "1950-??-??"
    assert merge_value("김천일", "김천이") == "김천이"


def test_턴_기록과_requested_slot():
    session = create_session()
    turn = add_turn(session, "네", [inform("consent", True)])
    assert (turn.turn_index, turn.requested_slot) == (0, "consent")
    assert session.turns == [turn]


def test_모든_슬롯을_물으면_끝나고_더_보내면_SessionDone():
    session = create_session()
    while (slot := next_slot(session)) is not None:
        add_turn(session, "몰라요", [uncertain(slot)])
    assert len(session.turns) == len(session.slot_values)
    with pytest.raises(SessionDone):
        add_turn(session, "하나 더", [])
