import re
import threading

import numpy as np

KNOWN_HALLUCINATIONS = {
    "thank you",
    "thank you very much",
    "thanks for watching",
    "thank you for watching",
    "you",
    "so",
    "subtítulos realizados por la comunidad de amara.org",
    "gracias por ver el video",
    "gracias",
    "música",
    "music",
}
NO_SPEECH_THRESHOLD = 0.6
LOW_CONFIDENCE_LOGPROB = -1.0


def normalize(text):
    return re.sub(r"[^\w\s.']", "", text.lower()).strip(" .")


def is_hallucination(text):
    cleaned = normalize(text)
    if not cleaned or cleaned in KNOWN_HALLUCINATIONS:
        return True
    words = cleaned.split()
    return len(words) >= 6 and len(set(words)) <= 2


def confident_text(segments):
    kept = [
        segment["text"].strip()
        for segment in segments
        if not (
            segment.get("no_speech_prob", 0) > NO_SPEECH_THRESHOLD
            and segment.get("avg_logprob", 0) < LOW_CONFIDENCE_LOGPROB
        )
    ]
    return " ".join(part for part in kept if part).strip()


class Transcriber:
    def __init__(self, model):
        self.model = model
        self.lock = threading.Lock()

    def warmup(self):
        self.transcribe(np.zeros(16000, dtype=np.int16), "en")

    def transcribe(self, audio, language=None):
        import mlx_whisper

        with self.lock:
            result = mlx_whisper.transcribe(
                audio.astype(np.float32) / 32768.0,
                path_or_hf_repo=self.model,
                language=language,
                condition_on_previous_text=False,
            )
        segments = result.get("segments")
        text = confident_text(segments) if segments else result["text"].strip()
        if is_hallucination(text):
            return "", result.get("language", language)
        return text, result.get("language", language)
