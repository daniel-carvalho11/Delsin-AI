"""Configuração central do Delsin.

Todos os caminhos usam pathlib e seguem a especificação XDG do Linux
(~/.local/share, ~/.cache), com override por variáveis de ambiente.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "Delsin"
APP_VERSION = "0.1.0"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _xdg_dir(env_var: str, fallback: Path) -> Path:
    value = os.environ.get(env_var)
    return Path(value).expanduser() if value else fallback


DATA_DIR = _xdg_dir("XDG_DATA_HOME", Path.home() / ".local" / "share") / "delsin"
CACHE_DIR = _xdg_dir("XDG_CACHE_HOME", Path.home() / ".cache") / "delsin"
LOG_DIR = DATA_DIR / "logs"


@dataclass(frozen=True)
class VoiceSettings:
    language: str = "pt-BR"
    # Nome (parcial) do dispositivo de entrada. "pipewire"/"default" passam pelo
    # servidor de áudio; abrir um "hw:X,Y" direto disputa o hardware com o PipeWire.
    preferred_input_devices: tuple[str, ...] = ("pipewire", "default")
    ambient_calibration_s: float = 0.5
    listen_timeout_s: float = 5.0
    phrase_time_limit_s: float = 10.0
    recognition_timeout_s: float = 8.0
    tts_voice: str = "pt-br"
    tts_rate: int = 170
    tts_timeout_s: float = 30.0
    tts_queue_size: int = 10


@dataclass(frozen=True)
class CoreSettings:
    skill_timeout_s: float = 10.0
    min_confidence: float = 0.5
    max_input_chars: int = 2000
    skill_workers: int = 4


@dataclass(frozen=True)
class Settings:
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    core: CoreSettings = field(default_factory=CoreSettings)
    debug: bool = False


def load_settings() -> Settings:
    lang = os.environ.get("DELSIN_LANG")
    voice = VoiceSettings(language=lang) if lang else VoiceSettings()
    return Settings(voice=voice, debug=os.environ.get("DELSIN_DEBUG") == "1")


def ensure_dirs() -> None:
    """Cria diretórios de dados com permissão restrita ao usuário (0700)."""
    for directory in (DATA_DIR, CACHE_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
