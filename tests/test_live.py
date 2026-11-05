import time

from meet_copilot.events import EventBus
from meet_copilot.live import LiveSession
from meet_copilot.store import list_sessions
from tests.fakes import FakeChat, FakeTranscriber, ScriptedSource, advice_or_summary, amplitude_vad, echo_translation, settings

SPEECH = [False] * 3 + [True] * 12 + [False] * 6


def run_session(tmp_path, sources, transcriber, **overrides):
    config = settings(tmp_path, **overrides)
    bus = EventBus()
    chats = (FakeChat("haiku", echo_translation), FakeChat("sonnet", advice_or_summary))
    session = LiveSession(config, bus, transcriber, None, "Demo", "ctx", sources, amplitude_vad, chats)
    session.start()
    deadline = time.time() + 5
    while time.time() < deadline and not any(event["type"] == "advice" for event in bus.history):
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
    chats = (FakeChat("haiku", echo_translation), FakeChat("sonnet", advice_or_summary))
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
    chats = (FakeChat("haiku", echo_translation), FakeChat("sonnet", advice_or_summary))
    session = LiveSession(config, bus, FakeTranscriber({}), None, "Demo", "", [], amplitude_vad, chats)
    session.start()
    session.ask("¿Qué les digo?")
    deadline = time.time() + 5
    while time.time() < deadline and not events(bus, "advice"):
        time.sleep(0.05)
    session.stop()
    assert events(bus, "advice")[0]["consulta"] == "¿Qué les digo?"
    assert events(bus, "summary")[0]["markdown"] == ""
