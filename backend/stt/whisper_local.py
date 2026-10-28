from stt.base import STTEngine, Transcript, UnsupportedAudio

# Whisper는 16kHz 샘플만 받는다. 디코딩한 샘플 수를 이 값으로 나누면 음성 길이(초)
SAMPLE_RATE = 16000


class WhisperLocalEngine(STTEngine):
    """faster-whisper로 이 서버의 GPU에서 Whisper large-v3-turbo를 돌리는 엔진."""

    name = "whisper-large-v3-turbo"

    def __init__(self):
        # 모델 라이브러리는 무거우므로 stub 엔진만 쓰는 로컬 개발·테스트에서는 불러오지 않도록 여기서 import한다
        from faster_whisper import WhisperModel

        # 모델을 GPU에 한 번만 올려 두고 이후 요청에서 재사용한다
        self.model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")

    def transcribe(self, audio_path: str) -> Transcript:
        from faster_whisper.audio import decode_audio

        # 먼저 디코딩만 해서 형식 오류와 음성 길이를 전사 전에 확인한다 (webm, m4a, mp3, wav 등을 PyAV가 읽는다)
        try:
            samples = decode_audio(audio_path, sampling_rate=SAMPLE_RATE)
        except Exception as error:
            raise UnsupportedAudio(str(error)) from error
        duration = len(samples) / SAMPLE_RATE

        # vad_filter: 무음 구간을 먼저 잘라내 "감사합니다" 같은 환각을 막는다
        segments, _ = self.model.transcribe(samples, language="ko", vad_filter=True)
        text = "".join(segment.text for segment in segments).strip()
        return Transcript(text=text, duration=duration)
