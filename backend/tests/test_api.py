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
