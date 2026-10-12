from abc import ABC, abstractmethod


class STTEngine(ABC):
    """모든 STT 엔진이 구현해야 하는 추상 클래스."""

    # 응답의 sttEngine 값으로 쓰는 엔진 이름 (예: "whisper-large-v3-turbo")
    name: str

    @abstractmethod
    def transcribe(self, audio_path: str) -> str:
        """음성 파일 경로를 받아 전사문을 돌려준다. 말소리가 없으면 빈 문자열."""
