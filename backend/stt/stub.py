from stt.base import STTEngine, Transcript


class StubEngine(STTEngine):
    """음성 내용과 상관없이 정해진 문장을 return하는 stub 엔진. GPU 없는 로컬 개발용."""

    name = "stub"

    def __init__(self, text: str = "공일공에 일이삼사에 오육칠팔", duration: float = 3.0):
        self.text = text
        self.duration = duration

    def transcribe(self, audio_path: str) -> Transcript:
        return Transcript(text=self.text, duration=self.duration)
