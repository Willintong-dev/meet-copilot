import json
import logging
import queue
import threading
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse

from meet_copilot.audio import MicrophoneSource, SystemAudioSource
from meet_copilot.live import LiveSession
from meet_copilot.responder import LENGTHS
from meet_copilot.store import compose_context, list_briefs, list_sessions, read_brief, read_session_file

log = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 15


def default_sources(settings):
    sources = [SystemAudioSource()]
    if settings.capture_microphone:
        sources.append(MicrophoneSource())
    return sources


class Controller:
    def __init__(self, settings, bus, transcriber, runner, session_factory=LiveSession, sources_factory=default_sources):
        self.settings = settings
        self.bus = bus
        self.transcriber = transcriber
        self.runner = runner
        self.session_factory = session_factory
        self.sources_factory = sources_factory
        self.session = None
        self.lock = threading.Lock()

    def state(self):
        return {
            "running": self.session is not None,
            "session": self.session.store.id if self.session else None,
            "title": self.session.title if self.session else None,
            "briefs": list_briefs(self.settings.briefs_dir),
            "sessions": list_sessions(self.settings.sessions_dir),
            "user_name": self.settings.user_name,
            "answer_length": self.settings.answer_length,
        }

    def start(self, title, brief_name, notes, previous_ids, answer_length=None):
        with self.lock:
            if self.session is not None:
                raise RuntimeError("Ya hay una llamada en curso")
            titles = {meta["id"]: meta["title"] for meta in list_sessions(self.settings.sessions_dir)}
            previous = [
                (titles.get(session_id, session_id), read_session_file(self.settings.sessions_dir, session_id, "summary.md"))
                for session_id in previous_ids
            ]
            brief = read_brief(self.settings.briefs_dir, brief_name) if brief_name else ""
            context = compose_context(notes, brief, previous)
            self.bus.clear_history()
            settings = replace(self.settings, answer_length=answer_length) if answer_length in LENGTHS else self.settings
            self.session = self.session_factory(
                settings,
                self.bus,
                self.transcriber,
                self.runner,
                title or "Llamada",
                context,
                self.sources_factory(settings),
            )
            self.session.start()
            return self.session.store.id

    def stop(self):
        with self.lock:
            session, self.session = self.session, None
        if session is None:
            raise RuntimeError("No hay una llamada en curso")
        threading.Thread(target=session.stop, daemon=True, name="session-stop").start()
        return session.store.id

    def shutdown(self, server):
        with self.lock:
            session, self.session = self.session, None
        if session is not None:
            session.stop()
        server.shutdown()

    def ask(self, question):
        if self.session is None:
            raise RuntimeError("No hay una llamada en curso")
        self.session.ask(question)


def make_handler(controller):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            log.debug(format, *args)

        def do_GET(self):
            url = urlparse(self.path)
            query = {key: values[0] for key, values in parse_qs(url.query).items()}
            if url.path == "/":
                return self._send(HTTPStatus.OK, resources.files("meet_copilot").joinpath("static/index.html").read_bytes(), "text/html; charset=utf-8")
            if url.path == "/api/state":
                return self._json(controller.state())
            if url.path == "/api/brief":
                return self._json({"content": read_brief(controller.settings.briefs_dir, query.get("name", ""))})
            if url.path == "/api/session-file":
                content = read_session_file(controller.settings.sessions_dir, query.get("id", ""), query.get("name", "summary.md"))
                return self._json({"content": content})
            if url.path == "/api/events":
                return self._events()
            return self._json({"error": "no encontrado"}, HTTPStatus.NOT_FOUND)

        def do_POST(self):
            url = urlparse(self.path)
            try:
                body = self._body()
                if url.path == "/api/start":
                    session_id = controller.start(
                        body.get("title", ""),
                        body.get("brief", ""),
                        body.get("notes", ""),
                        body.get("previous", []),
                        body.get("answer_length"),
                    )
                    return self._json({"session": session_id})
                if url.path == "/api/stop":
                    return self._json({"session": controller.stop()})
                if url.path == "/api/quit":
                    threading.Thread(target=controller.shutdown, args=(self.server,), daemon=True).start()
                    return self._json({"ok": True})
                if url.path == "/api/ask":
                    question = body.get("question", "").strip()
                    if not question:
                        raise ValueError("La pregunta está vacía")
                    controller.ask(question)
                    return self._json({"ok": True})
            except (RuntimeError, ValueError, json.JSONDecodeError) as error:
                return self._json({"error": str(error)}, HTTPStatus.CONFLICT)
            return self._json({"error": "no encontrado"}, HTTPStatus.NOT_FOUND)

        def _events(self):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            subscriber = controller.bus.subscribe()
            try:
                while True:
                    try:
                        event = subscriber.get(timeout=HEARTBEAT_SECONDS)
                        chunk = f"event: {event['type']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                    except queue.Empty:
                        chunk = ": ping\n\n"
                    self.wfile.write(chunk.encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                controller.bus.unsubscribe(subscriber)

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}")

        def _json(self, payload, status=HTTPStatus.OK):
            self._send(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def _send(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def serve(controller, host, port):
    server = ThreadingHTTPServer((host, port), make_handler(controller))
    server.daemon_threads = True
    return server
