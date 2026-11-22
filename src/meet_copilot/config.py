import os
import pwd
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def account_first_name():
    full_name = pwd.getpwuid(os.getuid()).pw_gecos.strip()
    return full_name.split()[0] if full_name else "Usuario"


@dataclass
class Settings:
    home: Path = field(default_factory=lambda: Path(os.environ.get("MEET_COPILOT_HOME", PROJECT_ROOT / "data")))
    user_name: str = field(default_factory=lambda: account_first_name())
    whisper_model: str = "mlx-community/whisper-large-v3-turbo"
    call_language: str = "en"
    my_language: str = "es"
    translator_model: str = "haiku"
    copilot_model: str = "sonnet"
    answer_model: str = "haiku"
    answer_length: str = "desarrollada"
    host: str = "127.0.0.1"
    port: int = 8777
    silence_ms: int = 500
    max_segment_seconds: int = 12
    copilot_interval_seconds: int = 20
    copilot_max_turns: int = 50
    echo_overlap_ratio: float = 0.5
    capture_microphone: bool = True
    echo_window_seconds: float = 6.0

    @property
    def sessions_dir(self):
        return self.home / "sessions"

    @property
    def briefs_dir(self):
        return self.home / "briefs"


def load_settings(path=PROJECT_ROOT / "config.toml"):
    settings = Settings()
    if path.exists():
        known = {item.name for item in fields(Settings)}
        for key, value in tomllib.loads(path.read_text()).items():
            if key in known:
                setattr(settings, key, Path(value).expanduser() if key == "home" else value)
    settings.sessions_dir.mkdir(parents=True, exist_ok=True)
    settings.briefs_dir.mkdir(parents=True, exist_ok=True)
    return settings
