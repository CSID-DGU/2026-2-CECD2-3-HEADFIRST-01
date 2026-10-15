import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ontology import load_questions

# 마지막 요청 후 이 시간이 지나면 세션을 지운다
SESSION_TTL = timedelta(minutes=30)


class SessionNotFound(Exception):
    """세션 ID가 없거나 만료됨. API에서는 SESSION_NOT_FOUND(404)로 응답한다."""


class SessionDone(Exception):
    """이미 끝난 대화에 턴을 보냄. API에서는 SESSION_DONE(409)으로 응답한다."""


@dataclass
class Turn:
    """발화 한 번의 기록."""

    turn_index: int
    requested_slot: str  # 이 턴에서 물어본 슬롯
    transcript: str
    frames: list[dict]  # 분류기 출력 [{slot, action, value}, ...]


@dataclass
class Session:
    """대화 하나의 상태."""

    id: str
    slot_values: dict  # {슬롯 이름: 값}. 처음엔 모두 None
    turns: list[Turn] = field(default_factory=list)
    last_used: datetime = field(default_factory=datetime.now)


# 서버 메모리에 두는 세션 저장소 {세션 ID: Session}. 서버를 재시작하면 사라진다
_sessions: dict[str, Session] = {}


def create_session() -> Session:
    """새 세션을 만들어 저장하고 돌려준다. ID 형식: 261012-153012-a3f9c1"""
    session_id = f"{datetime.now():%y%m%d-%H%M%S}-{secrets.token_hex(3)}"
    session = Session(id=session_id, slot_values={slot: None for slot in load_questions()})
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> Session:
    """세션을 찾아 돌려준다. 없거나 만료됐으면 SessionNotFound."""
    session = _sessions.get(session_id)
    if session is None:
        raise SessionNotFound(session_id)
    if datetime.now() - session.last_used > SESSION_TTL:
        del _sessions[session_id]
        raise SessionNotFound(session_id)
    return session


def is_complete(value) -> bool:
    """값이 있고 모르는 자리('?')도 없으면 완료."""
    return value is not None and not (isinstance(value, str) and "?" in value)


def next_slot(session: Session) -> str | None:
    """다음에 물을 슬롯. 아직 안 물었고 완료되지 않은 첫 슬롯이며, 없으면 None(대화 종료)."""
    asked = {turn.requested_slot for turn in session.turns}
    for slot, value in session.slot_values.items():
        if slot not in asked and not is_complete(value):
            return slot
    return None


def merge_value(old, new):
    """이전 값에 '?'가 있으면 그 자리만 새 값으로 채운다. 그 외에는 새 값으로 덮어쓴다."""
    if isinstance(old, str) and "?" in old and isinstance(new, str) and len(old) == len(new):
        return "".join(n if o == "?" else o for o, n in zip(old, new))
    return new


def apply_frames(session: Session, frames: list[dict]) -> None:
    """분류 결과를 슬롯 값에 반영한다. inform만 저장하고 uncertain은 무시한다."""
    for frame in frames:
        slot = frame["slot"]
        if frame["action"] == "inform" and slot in session.slot_values:
            session.slot_values[slot] = merge_value(session.slot_values[slot], frame["value"])


def add_turn(session: Session, transcript: str, frames: list[dict]) -> Turn:
    """지금 묻고 있는 슬롯에 대한 답을 기록하고 슬롯 값을 갱신한다. 대화가 끝났으면 SessionDone."""
    requested_slot = next_slot(session)
    if requested_slot is None:
        raise SessionDone(session.id)
    apply_frames(session, frames)
    turn = Turn(len(session.turns), requested_slot, transcript, frames)
    session.turns.append(turn)
    session.last_used = datetime.now()
    return turn
