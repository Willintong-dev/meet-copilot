import json
import threading
import urllib.error
import urllib.request

import pytest

from meet_copilot.events import EventBus
from meet_copilot.server import Controller, serve
from meet_copilot.store import SessionStore
from tests.fakes import settings


class FakeSession:
    instances = []

    def __init__(self, config, bus, transcriber, runner, title, context, sources):
        self.title = title
        self.context = context
        self.config = config
        self.bus = bus
        self.questions = []
        self.stopped = threading.Event()
        self.store = SessionStore(config.sessions_dir, title, context)
        FakeSession.instances.append(self)

    def start(self):
        self.bus.publish("status", {"state": "listening"})

    def ask(self, question):
        self.questions.append(question)

    def stop(self):
        self.stopped.set()


@pytest.fixture
def app(tmp_path):
    config = settings(tmp_path)
    (config.briefs_dir / "2026-11-05-acme.md").write_text("Acme usa Stripe")
    previous = SessionStore(config.sessions_dir, "Kickoff Acme", "")
    previous.finish([], "Acordamos piloto")
    controller = Controller(config, EventBus(), None, None, FakeSession, lambda config: [])
    server = serve(controller, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield controller, f"http://127.0.0.1:{server.server_address[1]}", previous.id
    server.shutdown()
    server.server_close()


def call(base, path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_serves_ui(app):
    controller, base, _ = app
    with urllib.request.urlopen(base + "/", timeout=5) as response:
        assert b"Meet Copilot" in response.read()


def test_state_lists_briefs_and_sessions(app):
    controller, base, previous_id = app
    status, state = call(base, "/api/state")
    assert status == 200
    assert state["briefs"] == ["2026-11-05-acme.md"]
    assert state["sessions"][0]["id"] == previous_id
    assert state["running"] is False
    assert state["answer_length"] == "desarrollada"


def test_start_composes_context_and_rejects_second_start(app):
    controller, base, previous_id = app
    status, body = call(base, "/api/start", {"title": "Demo", "brief": "2026-11-05-acme.md", "notes": "Cerrar piloto", "previous": [previous_id]})
    assert status == 200
    session = FakeSession.instances[-1]
    assert "Cerrar piloto" in session.context
    assert "Acme usa Stripe" in session.context
    assert "Llamada anterior: Kickoff Acme\nAcordamos piloto" in session.context
    assert call(base, "/api/start", {"title": "Otra"})[0] == 409
    assert call(base, "/api/state")[1]["running"] is True


def test_ask_and_stop(app):
    controller, base, _ = app
    assert call(base, "/api/ask", {"question": "hola"})[0] == 409
    call(base, "/api/start", {"title": "Demo"})
    assert call(base, "/api/ask", {"question": "  "})[0] == 409
    assert call(base, "/api/ask", {"question": "¿Qué digo?"}) == (200, {"ok": True})
    session = FakeSession.instances[-1]
    assert session.questions == ["¿Qué digo?"]
    assert call(base, "/api/stop", {})[0] == 200
    assert session.stopped.wait(2)
    assert call(base, "/api/stop", {})[0] == 409


def test_events_stream_replays_history(app):
    controller, base, _ = app
    controller.bus.publish("line", {"id": 0, "text": "Hi"})
    with urllib.request.urlopen(base + "/api/events", timeout=5) as response:
        assert response.readline() == b"event: line\n"
        assert json.loads(response.readline().decode().removeprefix("data: ")) == {"id": 0, "text": "Hi"}


def test_session_file_and_brief_endpoints(app):
    controller, base, previous_id = app
    assert call(base, f"/api/session-file?id={previous_id}&name=summary.md")[1]["content"] == "Acordamos piloto"
    assert call(base, "/api/brief?name=2026-11-05-acme.md")[1]["content"] == "Acme usa Stripe"
    assert call(base, "/api/nada")[0] == 404


def test_quit_stops_running_session_and_server(tmp_path):
    config = settings(tmp_path)
    controller = Controller(config, EventBus(), None, None, FakeSession, lambda config: [])
    server = serve(controller, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    call(base, "/api/start", {"title": "Demo"})
    session = FakeSession.instances[-1]
    assert call(base, "/api/quit", {}) == (200, {"ok": True})
    thread.join(timeout=5)
    server.server_close()
    assert not thread.is_alive()
    assert session.stopped.is_set()


def test_start_applies_answer_length_only_to_that_call(app):
    controller, base, _ = app
    call(base, "/api/start", {"title": "Demo", "answer_length": "breve"})
    assert FakeSession.instances[-1].config.answer_length == "breve"
    assert controller.settings.answer_length == "desarrollada"
    call(base, "/api/stop", {})
    call(base, "/api/start", {"title": "Otra", "answer_length": "inventada"})
    assert FakeSession.instances[-1].config.answer_length == "desarrollada"
