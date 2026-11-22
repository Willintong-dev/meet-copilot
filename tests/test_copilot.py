import json

import pytest

from meet_copilot.copilot import Copilot, normalize_advice, render_lines, should_consult
from meet_copilot.store import Line
from tests.fakes import ADVICE, FakeChat, advice_or_summary, settings


def line(speaker, text, index=0):
    return Line(index, speaker, text, "en", 0.0)


def test_questions_wait_for_the_interval_because_the_responder_answers_them():
    assert not should_consult([line("them", "Can you send it?")], 1, 20)


def test_consults_after_interval_or_enough_lines():
    statement = [line("them", "We use Stripe today.")]
    assert not should_consult(statement, 5, 20)
    assert should_consult(statement, 21, 20)
    assert should_consult(statement * 6, 1, 20)
    assert not should_consult([], 100, 20)


def test_render_lines_marks_speakers():
    assert render_lines([line("them", "Hi"), line("me", "Hola")]) == "[ELLOS] Hi\n[YO] Hola"


def test_normalize_advice_fills_defaults_and_drops_empty_suggestions():
    advice = normalize_advice({"sugerencias": [{"en": "Sure", "es": "Claro"}, {"es": "sin inglés"}, "x"]})
    assert advice == {"resumen": "", "pregunta": None, "sugerencias": [{"en": "Sure", "es": "Claro"}], "pendientes": [], "nota": None}


def test_normalize_advice_rejects_non_objects():
    with pytest.raises(ValueError):
        normalize_advice([1, 2])


def test_system_prompt_includes_context_and_user(tmp_path):
    chat = FakeChat("sonnet", advice_or_summary)
    Copilot(chat, settings(tmp_path), "Cliente: Acme")
    assert "Cliente: Acme" in chat.system_prompt
    assert "[CONSULTA DE ANA]" in chat.system_prompt


def test_consult_and_private_question(tmp_path):
    chat = FakeChat("sonnet", advice_or_summary)
    copilot = Copilot(chat, settings(tmp_path), "")
    assert copilot.consult([line("them", "How much is it?")], []) == ADVICE
    copilot.ask("¿Qué precio doy?", [line("them", "Pricing?")], [])
    assert chat.prompts[-1] == "[ELLOS] Pricing?\n[CONSULTA DE ANA] ¿Qué precio doy?"


def test_compacts_context_after_max_turns(tmp_path):
    chat = FakeChat("sonnet", advice_or_summary)
    copilot = Copilot(chat, settings(tmp_path, copilot_max_turns=2), "ctx")
    transcript = [line("them", f"line {index}", index) for index in range(40)]
    for _ in range(3):
        copilot.consult([transcript[-1]], transcript)
    assert len(chat.resets) == 1
    assert "Hablan de precios" in chat.resets[0]
    assert "Enviar precios" in chat.resets[0]
    assert chat.prompts[-1].startswith("[ELLOS] line 15")


def test_summarize_uses_full_transcript_and_fresh_prompt(tmp_path):
    chat = FakeChat("sonnet", advice_or_summary)
    copilot = Copilot(chat, settings(tmp_path), "ctx")
    summary = copilot.summarize([line("them", "Let's do the pilot in March.")])
    assert summary.startswith("## Resumen")
    assert "Let's do the pilot in March." in chat.prompts[-1]
    assert "Resumes llamadas" in chat.resets[-1]
    assert "## Dudas que quedaron abiertas" in chat.prompts[-1]
    assert "## Términos y herramientas mencionados" in chat.prompts[-1]
