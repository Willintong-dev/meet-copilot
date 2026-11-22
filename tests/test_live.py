import time

from meet_copilot.events import EventBus
from meet_copilot.live import LiveSession
from meet_copilot.store import list_sessions
from meet_copilot.store import Line
from tests.fakes import ANSWER, FakeChat, FakeTranscriber, ScriptedSource, amplitude_vad, settings, three_chats

SPEECH = [False] * 3 + [True] * 12 + [False] * 6


def run_session(tmp_path, sources, transcriber, wait_for=("advice",), **overrides):
    config = settings(tmp_path, **overrides)
    bus = EventBus()
    chats = three_chats()
    session = LiveSession(config, bus, transcriber, None, "Demo", "ctx", sources, amplitude_vad, chats)
    session.start()
    deadline = time.time() + 5
    while time.time() < deadline and not any(event["type"] in wait_for for event in bus.history):
        time.sleep(0.05)
    session.stop()
    return session, bus, chats


def events(bus, kind):
    return [event["data"] for event in bus.history if event["type"] == kind]


def test_full_flow_transcribes_translates_advises_and_summarizes(tmp_path):
    transcriber = FakeTranscriber({"them": "Can you share the pricing?"})
    session, bus, chats = run_session(tmp_path, [ScriptedSource("them", SPEECH)], transcriber)
    assert [line["text"] for line in events(bus, "line")] == ["Can you share the pricing?"]
    assert events(bus, "translation") == [{"id": 0, "translation": "ES: Can you share the pricing?"}]
    assert events(bus, "advice")[0]["pregunta"] == "Te preguntan el precio"
    assert events(bus, "summary")[0]["markdown"].startswith("## Resumen")
    assert events(bus, "status")[-1] == {"state": "idle"}
    assert transcriber.calls == ["en"]
    assert all(chat.closed for chat in chats)
    assert list_sessions(tmp_path / "sessions")[0]["has_summary"]


def test_spanish_lines_from_me_are_not_translated(tmp_path):
    transcriber = FakeTranscriber({"me": "Sí, claro"})
    session, bus, chats = run_session(tmp_path, [ScriptedSource("me", SPEECH)], transcriber)
    assert [line["text"] for line in events(bus, "line")] == ["Sí, claro"]
    assert events(bus, "translation") == []
    assert transcriber.calls == [None]


def test_microphone_echo_of_them_is_dropped(tmp_path):
    config = settings(tmp_path)
    bus = EventBus()
    chats = three_chats()
    transcriber = FakeTranscriber({"me": "We use Stripe."})
    session = LiveSession(config, bus, transcriber, None, "Demo", "", [ScriptedSource("me", SPEECH)], amplitude_vad, chats)
    now = time.time()
    for offset in range(-200, 200):
        session.activity.record(now + offset / 10, True)
    session.start()
    time.sleep(0.5)
    session.stop()
    assert events(bus, "line") == []
    assert transcriber.calls == []


def test_private_question_reaches_copilot(tmp_path):
    config = settings(tmp_path, copilot_interval_seconds=999)
    bus = EventBus()
    chats = three_chats()
    session = LiveSession(config, bus, FakeTranscriber({}), None, "Demo", "", [], amplitude_vad, chats)
    session.start()
    session.ask("¿Qué les digo?")
    deadline = time.time() + 5
    while time.time() < deadline and not events(bus, "advice"):
        time.sleep(0.05)
    session.stop()
    assert events(bus, "advice")[0]["consulta"] == "¿Qué les digo?"
    assert events(bus, "summary")[0]["markdown"] == ""


def test_question_gets_a_fast_answer_saved_with_the_session(tmp_path):
    transcriber = FakeTranscriber({"them": "Can you share the pricing?"})
    session, bus, chats = run_session(tmp_path, [ScriptedSource("them", SPEECH)], transcriber, wait_for=("answer",), copilot_interval_seconds=999)
    assert events(bus, "question")[0]["text"] == "Can you share the pricing?"
    answer = events(bus, "answer")[0]
    assert answer["respuesta_en"] == ANSWER["respuesta_en"]
    assert answer["ids"] == [0]
    assert 'Posible pregunta a evaluar: "Can you share the pricing?"' in chats[2].prompts[0]
    transcript = (session.store.dir / "transcript.md").read_text()
    assert "## Preguntas y respuestas sugeridas" in transcript
    assert "Sugerido: Sure, I will send [the pricing sheet] today." in transcript


def test_statements_do_not_reach_the_responder(tmp_path):
    transcriber = FakeTranscriber({"them": "We shipped the release yesterday."})
    session, bus, chats = run_session(tmp_path, [ScriptedSource("them", SPEECH)], transcriber)
    assert events(bus, "question") == []
    assert chats[2].prompts == []


def test_responder_rejection_dismisses_the_question(tmp_path):
    config = settings(tmp_path, copilot_interval_seconds=999)
    bus = EventBus()
    translator, copilot, _ = three_chats()
    rejecting = FakeChat("haiku", lambda prompt: '{"es_pregunta": false}')
    transcriber = FakeTranscriber({"them": "Why does this matter? Well, because it scales."})
    session = LiveSession(config, bus, transcriber, None, "Demo", "", [ScriptedSource("them", SPEECH)], amplitude_vad, (translator, copilot, rejecting))
    session.start()
    deadline = time.time() + 5
    while time.time() < deadline and not events(bus, "question_dismissed"):
        time.sleep(0.05)
    session.stop()
    assert events(bus, "question_dismissed") == [{"ids": [0]}]
    assert events(bus, "answer") == []


def test_microphone_lines_in_unexpected_languages_are_dropped(tmp_path):
    session = LiveSession(settings(tmp_path), EventBus(), None, None, "Demo", "", [], amplitude_vad, three_chats())
    assert session._expected_language("es")
    assert session._expected_language("en")
    assert not session._expected_language("ko")


def test_microphone_line_repeating_them_is_dropped_as_echo(tmp_path):
    session = LiveSession(settings(tmp_path), EventBus(), None, None, "Demo", "", [], amplitude_vad, three_chats())
    session.lines.append(Line(0, "them", "We use Stripe for payments today.", "en", 100.0))
    assert session._add_line("me", "we use stripe for payments today", "en", 102.0) is None
    assert session._add_line("me", "we use stripe for payments today", "en", 120.0) is not None
    assert session._add_line("me", "Sounds good to me.", "en", 101.0) is not None
