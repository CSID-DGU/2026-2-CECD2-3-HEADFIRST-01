import os
from functools import cache

from stt.base import STTEngine
from stt.stub import StubEngine
from stt.whisper_local import WhisperLocalEngine

# STT_ENGINE 환경변수 값 → 엔진 클래스
ENGINES = {
    "stub": StubEngine,
    "whisper_local": WhisperLocalEngine,
}


@cache
def get_engine() -> STTEngine:
    """STT_ENGINE으로 고른 엔진을 돌려준다. 처음 한 번만 만들고 이후에는 같은 객체를 재사용한다."""
    key = os.getenv("STT_ENGINE", "stub")
    if key not in ENGINES:
        raise ValueError(f"알 수 없는 STT_ENGINE: {key!r} (가능한 값: {', '.join(ENGINES)})")
    return ENGINES[key]()
