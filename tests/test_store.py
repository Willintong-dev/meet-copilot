import json

from meet_copilot.store import (
    Line,
    SessionStore,
    compose_context,
    list_briefs,
    list_sessions,
    read_brief,
    read_session_file,
    slugify,
)


def test_slugify_strips_accents_and_symbols():
    assert slugify("Demo con Acmé — SSO & pricing!") == "demo-con-acme-sso-pricing"
    assert slugify("¿?") == "llamada"


def test_session_lifecycle_writes_all_files(tmp_path):
    store = SessionStore(tmp_path, "Demo Acme", "contexto", now=lambda: 1_700_000_000)
    line = Line(0, "them", "Hello", "en", 1_700_000_001, "Hola")
    store.record_line(line)
    store.record_advice({"resumen": "x"})
    store.finish([line], "## Resumen\nok")
    assert json.loads((store.dir / "transcript.jsonl").read_text())["translation"] == "Hola"
    assert json.loads((store.dir / "copilot.jsonl").read_text())["resumen"] == "x"
    assert "> Hola" in (store.dir / "transcript.md").read_text()
    assert (store.dir / "context.md").read_text() == "contexto"
    sessions = list_sessions(tmp_path)
    assert sessions[0]["title"] == "Demo Acme"
    assert sessions[0]["has_summary"]
    assert sessions[0]["ended_at"] is not None
    assert read_session_file(tmp_path, store.id, "summary.md") == "## Resumen\nok"


def test_session_files_cannot_escape_directory(tmp_path):
    (tmp_path / "secret.md").write_text("no")
    assert read_session_file(tmp_path / "sessions", "..", "secret.md") == ""
    assert read_brief(tmp_path / "briefs", "../secret.md") == ""


def test_briefs_listed_newest_first_and_only_markdown(tmp_path):
    (tmp_path / "a.md").write_text("A")
    (tmp_path / "b.txt").write_text("B")
    assert list_briefs(tmp_path) == ["a.md"]
    assert read_brief(tmp_path, "a.md") == "A"
    assert read_brief(tmp_path, "b.txt") == ""


def test_compose_context_skips_empty_parts():
    context = compose_context("  ", "Brief", [("Llamada 1", "Resumen 1"), ("Llamada 2", "")])
    assert context == "## Brief preparado\nBrief\n\n## Llamada anterior: Llamada 1\nResumen 1"
