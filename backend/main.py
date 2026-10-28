import json
import os
import tempfile
import time
from pathlib import Path
from typing import Annotated

import openai
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from classifier import classify
from ontology import load_questions
from session import (
    Session,
    SessionDone,
    SessionNotFound,
    Turn,
    add_turn,
    create_session,
    get_session,
    next_slot,
)
from stt import get_engine
from stt.base import UnsupportedAudio

app = FastAPI(title="의도-엔티티 분류기 백엔드")

# 프론트(Vercel)에서 이 서버를 부를 수 있도록 허용할 주소. 여러 개면 쉼표로 구분한다
CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])

# 음성 턴 한 번에 받는 파일 제한 (API 명세: 최대 60초·10MB)
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_AUDIO_SECONDS = 60


# ---------- 응답 형식 ----------


class ApiError(Exception):
    """API 에러. 핸들러가 공통 응답 형식의 실패 응답으로 바꾼다."""

    def __init__(self, status_code: int, error_code: str, message: str):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


def success(message: str, data: dict, status_code: int = 200) -> JSONResponse:
    """성공 응답 {success: true, message, data}."""
    return JSONResponse(status_code=status_code, content={"success": True, "message": message, "data": data})


def failure(status_code: int, error_code: str, message: str) -> JSONResponse:
    """실패 응답 {success: false, message, data: {errorCode}}."""
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "message": message, "data": {"errorCode": error_code}},
    )


@app.exception_handler(ApiError)
def handle_api_error(request: Request, error: ApiError):
    return failure(error.status_code, error.error_code, error.message)


@app.exception_handler(SessionNotFound)
def handle_session_not_found(request: Request, error: SessionNotFound):
    return failure(404, "SESSION_NOT_FOUND", "세션이 없거나 만료되었습니다. 새 대화를 시작해 주세요.")


@app.exception_handler(SessionDone)
def handle_session_done(request: Request, error: SessionDone):
    return failure(409, "SESSION_DONE", "이미 끝난 대화입니다. 새 대화를 시작해 주세요.")


@app.exception_handler(RequestValidationError)
def handle_invalid_request(request: Request, error: RequestValidationError):
    return failure(422, "INVALID_REQUEST", "요청 형식이 올바르지 않습니다.")


# ---------- 응답 data 만들기 ----------


def question(slot: str | None) -> dict | None:
    """슬롯을 {slot, text} 질문으로 만든다. 슬롯이 없으면(대화 끝) None."""
    if slot is None:
        return None
    return {"slot": slot, "text": load_questions()[slot]}


def session_state(session: Session) -> dict:
    """세션의 현재 상태: 슬롯 순서, 슬롯 값, 다음 질문, 종료 여부."""
    slot = next_slot(session)
    return {
        "sessionId": session.id,
        "slotOrder": list(load_questions()),
        "slotValues": session.slot_values,
        "nextQuestion": question(slot),
        "done": slot is None,
    }


def turn_record(turn: Turn) -> dict:
    """턴 하나의 기록. turnIndex는 세션 안에서 0부터 세므로 1을 더해 1부터 보여 준다."""
    return {
        "turnIndex": turn.turn_index + 1,
        "requestedSlot": turn.requested_slot,
        "transcript": turn.transcript,
        "frames": turn.frames,
    }


# ---------- API ----------


@app.get("/health", summary="서버 상태 확인")
def health():
    return {"status": "ok"}


@app.post("/api/sessions", status_code=201, summary="대화 시작")
def start_session():
    """새 대화를 시작하고 첫 질문을 돌려준다."""
    session = create_session()
    return success("대화가 시작되었습니다.", session_state(session), status_code=201)


@app.get("/api/sessions/{session_id}", summary="대화 상태 조회")
def read_session(session_id: str):
    """세션의 현재 상태와 지금까지의 턴 기록을 돌려준다."""
    session = get_session(session_id)
    data = session_state(session) | {"turns": [turn_record(turn) for turn in session.turns]}
    return success("세션 조회에 성공했습니다.", data)


class TextTurnRequest(BaseModel):
    # 앞뒤 공백을 지운 뒤 1자 이상이어야 한다
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def run_turn(session: Session, text: str, started: float, stt_engine: str | None, stt_ms: int | None) -> dict:
    """발화 텍스트를 분류해 세션에 반영하고 턴 결과 data를 만든다. 텍스트 턴과 음성 턴이 함께 쓴다.
    started는 요청 처리를 시작한 시각(perf_counter), stt_engine과 stt_ms는 음성 턴일 때만 값이 있다."""
    # 분류기에서 에러가 나면 턴을 기록하지 않고 세션도 그대로 둔다
    llm_started = time.perf_counter()
    try:
        frames, _ = classify(session, text)  # 두 번째 값(분류기 원래 출력)은 턴 로그 작업 때 쓴다
    except openai.APITimeoutError:
        raise ApiError(504, "LLM_TIMEOUT", "분류기 응답이 늦어 처리하지 못했습니다. 다시 시도해 주세요.")
    except (openai.APIError, json.JSONDecodeError):
        raise ApiError(502, "LLM_FAILED", "분류기 처리 중 오류가 발생했습니다. 다시 시도해 주세요.")
    llm_ms = round((time.perf_counter() - llm_started) * 1000)

    turn = add_turn(session, text, frames)
    slot = next_slot(session)
    return turn_record(turn) | {
        "slotValues": session.slot_values,
        "nextQuestion": question(slot),
        "done": slot is None,
        "sttEngine": stt_engine,
        "timingMs": {"stt": stt_ms, "llm": llm_ms, "total": round((time.perf_counter() - started) * 1000)},
    }


@app.post("/api/sessions/{session_id}/turns/text", summary="텍스트 턴 진행")
def text_turn(session_id: str, body: TextTurnRequest):
    """텍스트 발화 한 번을 분류해 세션에 반영하고, 결과와 다음 질문을 돌려준다. STT는 쓰지 않는다."""
    started = time.perf_counter()
    session = get_session(session_id)
    data = run_turn(session, body.text, started, stt_engine=None, stt_ms=None)
    return success("턴이 처리되었습니다.", data)


def transcribe_upload(audio: UploadFile) -> tuple[str, str, int]:
    """업로드된 음성 파일을 STT로 전사해 (전사문, 엔진 이름, STT 소요 ms)를 돌려준다.
    파일 크기·길이·형식·빈 전사문은 API 명세의 에러 코드로 바꾼다."""
    content = audio.file.read(MAX_AUDIO_BYTES + 1)  # 제한보다 1바이트만 더 읽어 초과 여부를 안다
    if len(content) > MAX_AUDIO_BYTES:
        raise ApiError(413, "AUDIO_TOO_LARGE", "음성 파일은 10MB·60초 이하여야 합니다. 짧게 다시 말씀해 주세요.")
    if not content:
        raise ApiError(400, "EMPTY_AUDIO", "음성이 비어 있습니다. 다시 말씀해 주세요.")

    # STT 엔진은 파일 경로를 받으므로 임시 파일로 저장했다가 끝나면 지운다. 확장자는 디코더가 형식을 고르는 힌트
    suffix = Path(audio.filename or "").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
        temp.write(content)
        temp_path = temp.name

    engine = get_engine()
    stt_started = time.perf_counter()
    try:
        transcript = engine.transcribe(temp_path)
    except UnsupportedAudio:
        raise ApiError(400, "UNSUPPORTED_AUDIO", "지원하지 않는 음성 형식이거나 파일이 손상되었습니다.")
    except Exception:  # noqa: BLE001 — STT 엔진이 내는 예외 종류(CUDA, ctranslate2 등)를 미리 알 수 없어 모두 STT_FAILED로 묶는다
        raise ApiError(502, "STT_FAILED", "음성을 인식하지 못했습니다. 다시 시도해 주세요.")
    finally:
        os.remove(temp_path)
    stt_ms = round((time.perf_counter() - stt_started) * 1000)

    if transcript.duration > MAX_AUDIO_SECONDS:
        raise ApiError(413, "AUDIO_TOO_LARGE", "음성 파일은 10MB·60초 이하여야 합니다. 짧게 다시 말씀해 주세요.")
    if not transcript.text:
        raise ApiError(400, "EMPTY_AUDIO", "말소리를 찾지 못했습니다. 다시 말씀해 주세요.")
    return transcript.text, engine.name, stt_ms


@app.post("/api/sessions/{session_id}/turns", summary="음성 턴 진행")
def audio_turn(session_id: str, audio: Annotated[UploadFile, File(description="사용자 발화 녹음 파일 (webm, ogg, m4a, mp3, wav)")]):
    """음성 발화 한 번을 STT로 전사한 뒤 텍스트 턴과 같은 방식으로 분류해 세션에 반영하고, 전사문·결과·다음 질문을 돌려준다."""
    started = time.perf_counter()
    session = get_session(session_id)  # 세션이 없거나 끝났으면 STT를 돌리기 전에 먼저 거른다
    if next_slot(session) is None:
        raise SessionDone(session.id)
    text, engine_name, stt_ms = transcribe_upload(audio)
    data = run_turn(session, text, started, stt_engine=engine_name, stt_ms=stt_ms)
    return success("턴이 처리되었습니다.", data)
