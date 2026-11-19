import json

import httpx2
import openai
import pytest
from fastapi.testclient import TestClient

import classifier
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_mode(monkeypatch):
    """테스트는 환경변수와 상관없이 mock 모드로 돌려 실제 서버를 부르지 않는다."""
    monkeypatch.setattr(classifier, "CLASSIFIER_MODE", "mock")


def start():
    """대화를 시작하고 세션 ID를 돌려준다."""
    return client.post("/api/sessions").json()["data"]["sessionId"]


def say(session_id, text):
    """텍스트 턴을 보내고 응답을 돌려준다."""
    return client.post(f"/api/sessions/{session_id}/turns/text", json={"text": text})


def fail_vllm(monkeypatch, error):
    """vllm 모드로 바꾸고, 분류기 호출이 error를 내게 한다."""

    def raise_error(messages):
        raise error

    monkeypatch.setattr(classifier, "CLASSIFIER_MODE", "vllm")
    monkeypatch.setattr(classifier, "call_vllm", raise_error)


def test_대화_시작은_201과_첫_질문():
    response = client.post("/api/sessions")
    body = response.json()
    assert response.status_code == 201
    assert body["success"] is True
    assert body["data"]["slotOrder"][0] == "consent"
    assert all(value is None for value in body["data"]["slotValues"].values())
    assert body["data"]["nextQuestion"] == {
        "slot": "consent",
        "text": "민원 접수를 위해 개인정보 수집에 동의하시나요?",
    }
    assert body["data"]["done"] is False


def test_텍스트_턴은_분류_결과와_다음_질문을_돌려준다():
    data = say(start(), "네 동의합니다").json()["data"]
    assert data["turnIndex"] == 1
    assert data["requestedSlot"] == "consent"
    assert data["frames"] == [{"slot": "consent", "action": "inform", "value": True}]
    assert data["slotValues"]["consent"] is True
    assert data["nextQuestion"]["slot"] == "name"
    assert data["sttEngine"] is None
    assert data["timingMs"]["stt"] is None
    assert set(data["timingMs"]) == {"stt", "llm", "total"}


def test_상태_조회는_턴_기록을_1부터_센다():
    session_id = start()
    say(session_id, "네")
    say(session_id, "김천일이요")
    data = client.get(f"/api/sessions/{session_id}").json()["data"]
    assert [turn["turnIndex"] for turn in data["turns"]] == [1, 2]
    assert data["slotValues"]["name"] == "김천일이요"
    assert data["nextQuestion"]["slot"] == "birth_date"


def test_없는_세션은_404():
    for response in [client.get("/api/sessions/없는-세션"), say("없는-세션", "네")]:
        assert response.status_code == 404
        assert response.json() == {
            "success": False,
            "message": "세션이 없거나 만료되었습니다. 새 대화를 시작해 주세요.",
            "data": {"errorCode": "SESSION_NOT_FOUND"},
        }


def test_모든_슬롯을_물으면_끝나고_더_보내면_409():
    session_id = start()
    while True:
        data = say(session_id, "몰라요").json()["data"]
        if data["done"]:
            break
    assert data["nextQuestion"] is None

    response = say(session_id, "하나 더")
    assert response.status_code == 409
    assert response.json()["data"]["errorCode"] == "SESSION_DONE"


@pytest.mark.parametrize("body", [{"text": ""}, {"text": "   "}, {}])
def test_text가_비었거나_없으면_422(body):
    response = client.post(f"/api/sessions/{start()}/turns/text", json=body)
    assert response.status_code == 422
    assert response.json()["data"]["errorCode"] == "INVALID_REQUEST"


def test_분류기_시간_초과는_504이고_상태가_그대로(monkeypatch):
    session_id = start()
    fail_vllm(monkeypatch, openai.APITimeoutError(request=httpx2.Request("POST", "http://vllm.test")))

    response = say(session_id, "네")
    assert response.status_code == 504
    assert response.json()["data"]["errorCode"] == "LLM_TIMEOUT"
    assert client.get(f"/api/sessions/{session_id}").json()["data"]["turns"] == []


def test_분류기_출력이_JSON이_아니면_502(monkeypatch):
    session_id = start()
    fail_vllm(monkeypatch, json.JSONDecodeError("JSON이 아님", "네 분석 결과는", 0))

    response = say(session_id, "네")
    assert response.status_code == 502
    assert response.json()["data"]["errorCode"] == "LLM_FAILED"


# ---------- 음성 턴 ----------

import main
from stt.base import UnsupportedAudio
from stt.stub import StubEngine


def use_engine(monkeypatch, engine):
    """음성 턴이 쓰는 STT 엔진을 바꾼다. 테스트는 GPU 없이 stub 엔진으로 돈다."""
    monkeypatch.setattr(main, "get_engine", lambda: engine)


def speak(session_id, content=b"fake-audio", filename="utt.webm"):
    """음성 턴을 보내고 응답을 돌려준다."""
    return client.post(f"/api/sessions/{session_id}/turns", files={"audio": (filename, content, "audio/webm")})


class FailingEngine(StubEngine):
    """transcribe에서 정해진 예외를 내는 엔진."""

    def __init__(self, error):
        super().__init__()
        self.error = error

    def transcribe(self, audio_path):
        raise self.error


def test_음성_턴은_전사문과_분류_결과를_돌려준다(monkeypatch):
    use_engine(monkeypatch, StubEngine(text="네 동의합니다"))
    data = speak(start()).json()["data"]
    assert data["turnIndex"] == 1
    assert data["requestedSlot"] == "consent"
    assert data["transcript"] == "네 동의합니다"
    assert data["frames"] == [{"slot": "consent", "action": "inform", "value": True}]
    assert data["nextQuestion"]["slot"] == "name"
    assert data["sttEngine"] == "stub"
    assert isinstance(data["timingMs"]["stt"], int)
    assert set(data["timingMs"]) == {"stt", "llm", "total"}


def test_음성_턴_뒤에_텍스트_턴을_이어서_보낼_수_있다(monkeypatch):
    use_engine(monkeypatch, StubEngine(text="네"))
    session_id = start()
    speak(session_id)
    data = say(session_id, "김천일이요").json()["data"]
    assert data["turnIndex"] == 2
    assert data["requestedSlot"] == "name"
    assert data["sttEngine"] is None


@pytest.mark.parametrize("content", [b"", b"x" * (10 * 1024 * 1024 + 1)])
def test_파일이_비었거나_10MB를_넘으면_거른다(monkeypatch, content):
    use_engine(monkeypatch, StubEngine())
    session_id = start()
    response = speak(session_id, content)
    assert response.status_code == (400 if not content else 413)
    assert response.json()["data"]["errorCode"] == ("EMPTY_AUDIO" if not content else "AUDIO_TOO_LARGE")
    assert client.get(f"/api/sessions/{session_id}").json()["data"]["turns"] == []


def test_60초를_넘으면_413(monkeypatch):
    use_engine(monkeypatch, StubEngine(duration=61))
    response = speak(start())
    assert response.status_code == 413
    assert response.json()["data"]["errorCode"] == "AUDIO_TOO_LARGE"


def test_전사문이_비면_400이고_상태가_그대로(monkeypatch):
    use_engine(monkeypatch, StubEngine(text=""))
    session_id = start()
    response = speak(session_id)
    assert response.status_code == 400
    assert response.json()["data"]["errorCode"] == "EMPTY_AUDIO"
    assert client.get(f"/api/sessions/{session_id}").json()["data"]["turns"] == []


@pytest.mark.parametrize(
    "error, status, error_code",
    [(UnsupportedAudio("decode failed"), 400, "UNSUPPORTED_AUDIO"), (RuntimeError("cuda"), 502, "STT_FAILED")],
)
def test_STT_오류는_에러_코드로_바꾼다(monkeypatch, error, status, error_code):
    use_engine(monkeypatch, FailingEngine(error))
    response = speak(start())
    assert response.status_code == status
    assert response.json()["data"]["errorCode"] == error_code


def test_audio_필드가_없으면_422():
    response = client.post(f"/api/sessions/{start()}/turns")
    assert response.status_code == 422
    assert response.json()["data"]["errorCode"] == "INVALID_REQUEST"


def test_음성_턴도_없는_세션은_404_끝난_세션은_409(monkeypatch):
    use_engine(monkeypatch, StubEngine())
    assert speak("없는-세션").status_code == 404

    session_id = start()
    while not say(session_id, "몰라요").json()["data"]["done"]:
        pass
    response = speak(session_id)
    assert response.status_code == 409
    assert response.json()["data"]["errorCode"] == "SESSION_DONE"
