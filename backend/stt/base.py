from abc import ABC, abstractmethod
from dataclasses import dataclass


class UnsupportedAudio(Exception):
    """음성 파일을 디코딩할 수 없음(지원하지 않는 형식, 깨진 파일). API에서는 UNSUPPORTED_AUDIO(400)로 응답한다."""


@dataclass
class Transcript:
    """STT 결과."""

    text: str  # 전사문. 말소리가 없으면 빈 문자열
    duration: float  # 음성 길이(초). 60초 제한 검사에 쓴다


class STTEngine(ABC):
    """모든 STT 엔진이 구현해야 하는 추상 클래스."""

    # 응답의 sttEngine 값으로 쓰는 엔진 이름 (예: "whisper-large-v3-turbo")
    name: str

    @abstractmethod
    def transcribe(self, audio_path: str) -> Transcript:
        """음성 파일 경로를 받아 전사문과 음성 길이를 돌려준다. 디코딩할 수 없으면 UnsupportedAudio."""
