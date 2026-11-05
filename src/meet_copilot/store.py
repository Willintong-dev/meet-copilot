import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Line:
    id: int
    speaker: str
    text: str
    language: str
    started_at: float
    translation: str | None = None


def slugify(text):
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:40] or "llamada"


def safe_name(name):
    return Path(name).name


class SessionStore:
    def __init__(self, sessions_dir, title, context, now=time.time):
        started = now()
        stamp = time.strftime("%Y-%m-%d-%H%M", time.localtime(started))
        self.id = f"{stamp}-{slugify(title)}"
        self.dir = Path(sessions_dir) / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.meta = {"id": self.id, "title": title, "started_at": started, "ended_at": None}
        self._write_meta()
        (self.dir / "context.md").write_text(context or "")

    def record_line(self, line):
        self._append("transcript.jsonl", asdict(line))

    def record_advice(self, advice):
        self._append("copilot.jsonl", {"at": time.time(), **advice})

    def finish(self, lines, summary):
        self.meta["ended_at"] = time.time()
        self._write_meta()
        (self.dir / "transcript.md").write_text(render_transcript(lines))
        if summary:
            (self.dir / "summary.md").write_text(summary)

    def _append(self, name, record):
        with (self.dir / name).open("a") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _write_meta(self):
        (self.dir / "meta.json").write_text(json.dumps(self.meta, ensure_ascii=False, indent=2))


def render_transcript(lines):
    rendered = []
    for line in lines:
        clock = time.strftime("%H:%M:%S", time.localtime(line.started_at))
        who = "Yo" if line.speaker == "me" else "Ellos"
        rendered.append(f"**{clock} {who}:** {line.text}")
        if line.translation:
            rendered.append(f"> {line.translation}")
        rendered.append("")
    return "\n".join(rendered)


def list_sessions(sessions_dir):
    sessions = []
    for meta_path in Path(sessions_dir).glob("*/meta.json"):
        meta = json.loads(meta_path.read_text())
        meta["has_summary"] = (meta_path.parent / "summary.md").exists()
        sessions.append(meta)
    return sorted(sessions, key=lambda meta: meta["started_at"], reverse=True)


def read_session_file(sessions_dir, session_id, name):
    path = Path(sessions_dir) / safe_name(session_id) / safe_name(name)
    return path.read_text() if path.exists() else ""


def list_briefs(briefs_dir):
    return sorted(
        (path.name for path in Path(briefs_dir).glob("*.md")),
        key=lambda name: (Path(briefs_dir) / name).stat().st_mtime,
        reverse=True,
    )


def read_brief(briefs_dir, name):
    path = Path(briefs_dir) / safe_name(name)
    return path.read_text() if path.exists() and path.suffix == ".md" else ""


def compose_context(notes, brief, previous_sessions):
    parts = []
    if notes.strip():
        parts.append(f"## Mis notas\n{notes.strip()}")
    if brief.strip():
        parts.append(f"## Brief preparado\n{brief.strip()}")
    for title, summary in previous_sessions:
        if summary.strip():
            parts.append(f"## Llamada anterior: {title}\n{summary.strip()}")
    return "\n\n".join(parts)
