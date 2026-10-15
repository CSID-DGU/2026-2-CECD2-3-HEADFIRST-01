from stt.base import STTEngine


class WhisperLocalEngine(STTEngine):
    """faster-whisper로 이 서버의 GPU에서 Whisper large-v3-turbo를 돌리는 엔진."""

    name = "whisper-large-v3-turbo"

    def __init__(self):
        # faster-whisper는 requirements-stt.txt에만 있으므로, 이 엔진을 만들 때만 불러온다
        from faster_whisper import WhisperModel

        # 모델을 GPU에 한 번만 올려 두고 이후 요청에서 재사용한다
        self.model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")

    def transcribe(self, audio_path: str) -> str:
        # vad_filter: 무음 구간을 먼저 잘라내 "감사합니다" 같은 환각을 막는다
        segments, _ = self.model.transcribe(audio_path, language="ko", vad_filter=True)
        return "".join(segment.text for segment in segments).strip()
