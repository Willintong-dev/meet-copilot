import json

import pytest

from meet_copilot.responder import Responder, normalize_answer, responder_prompt
from meet_copilot.store import Line
from tests.fakes import ANSWER, FakeChat, answer_questions, settings


def test_prompt_includes_user_language_and_truncated_context(tmp_path):
    prompt = responder_prompt(settings(tmp_path), "§" * 9000)
    assert "Willintong" in prompt
    assert "inglés" in prompt
    assert prompt.count("§") == 4000


@pytest.mark.parametrize("length, expected", [("breve", "UNA frase"), ("desarrollada", "2 o 3 frases"), ("rara", "2 o 3 frases")])
def test_answer_prompt_carries_length_recent_lines_and_question(tmp_path, length, expected):
    chat = FakeChat("haiku", answer_questions)
    responder = Responder(chat, settings(tmp_path, answer_length=length))
    lines = [Line(index, "them", f"line {index}", "en", 0.0) for index in range(30)]
    assert responder.answer("Any questions?", lines)["respuesta_en"] == ANSWER["respuesta_en"]
    prompt = chat.prompts[0]
    assert expected in prompt
    assert "[ELLOS] line 10" in prompt and "[ELLOS] line 9\n" not in prompt
    assert prompt.endswith('Posible pregunta a evaluar: "Any questions?"')


def test_normalize_answer_returns_none_when_not_a_question():
    assert normalize_answer({"es_pregunta": False, "respuesta_en": "x"}) is None
    assert normalize_answer({"es_pregunta": True, "respuesta_en": ""}) is None


def test_normalize_answer_cleans_fields():
    answer = normalize_answer({"es_pregunta": True, "respuesta_en": " Sure. ", "confianza": "ALTA", "dirigida_a_mi": 1})
    assert answer == {"dirigida_a_mi": True, "pregunta_es": "", "respuesta_en": "Sure.", "respuesta_es": "", "confianza": "alta"}
    assert normalize_answer({"es_pregunta": True, "respuesta_en": "Ok", "confianza": "mucha"})["confianza"] is None


def test_normalize_answer_rejects_non_objects():
    with pytest.raises(ValueError):
        normalize_answer(json.loads("[1]"))
