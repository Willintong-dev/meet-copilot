import json

import numpy as np

from meet_copilot.audio import FRAME_SAMPLES
from meet_copilot.config import Settings

LOUD = 8000


def settings(tmp_path, **overrides):
    value = Settings(**{"home": tmp_path, "silence_ms": 90, "copilot_interval_seconds": 0, **overrides})
    value.sessions_dir.mkdir(parents=True, exist_ok=True)
    value.briefs_dir.mkdir(parents=True, exist_ok=True)
    return value


def frame(loud):
    return np.full(FRAME_SAMPLES, LOUD if loud else 0, dtype=np.int16)


def amplitude_vad():
    return lambda samples: bool(np.abs(samples).max() > 1000)


class ScriptedSource:
    def __init__(self, name, pattern):
        self.name = name
        self.pattern = pattern
        self.stopped = False

    def stop(self):
        self.stopped = True

    def frames(self):
        for loud in self.pattern:
            if self.stopped:
                return
            yield frame(loud)


class FakeTranscriber:
    def __init__(self, texts):
        self.texts = dict(texts)
        self.calls = []

    def transcribe(self, audio, language):
        self.calls.append(language)
        speaker = "them" if language == "en" else "me"
        return self.texts.get(speaker, ""), language or "es"


class FakeChat:
    def __init__(self, model, responder):
        self.model = model
        self.system_prompt = ""
        self.responder = responder
        self.prompts = []
        self.resets = []
        self.closed = False

    def ask(self, prompt, timeout=None):
        self.prompts.append(prompt)
        return self.responder(prompt)

    def warm(self):
        pass

    def reset(self, system_prompt=None):
        self.resets.append(system_prompt)
        if system_prompt is not None:
            self.system_prompt = system_prompt

    def close(self):
        self.closed = True


def echo_translation(prompt):
    return json.dumps([f"ES: {text}" for text in json.loads(prompt)], ensure_ascii=False)


ADVICE = {
    "resumen": "Hablan de precios",
    "pregunta": "Te preguntan el precio",
    "sugerencias": [{"en": "Let me confirm and get back to you.", "es": "Déjame confirmar y te respondo."}],
    "pendientes": ["Enviar precios"],
    "nota": None,
}


ANSWER = {
    "es_pregunta": True,
    "dirigida_a_mi": True,
    "pregunta_es": "¿Puedes compartir los precios?",
    "respuesta_en": "Sure, I will send [the pricing sheet] today.",
    "respuesta_es": "Claro, envío [la hoja de precios] hoy.",
    "confianza": "alta",
}


def answer_questions(prompt):
    return json.dumps(ANSWER, ensure_ascii=False)


def three_chats():
    return (FakeChat("haiku", echo_translation), FakeChat("sonnet", advice_or_summary), FakeChat("haiku", answer_questions))


def advice_or_summary(prompt):
    if prompt.startswith("Transcripción completa"):
        return "## Resumen\nHablaron de precios."
    return "```json\n" + json.dumps(ADVICE, ensure_ascii=False) + "\n```"
