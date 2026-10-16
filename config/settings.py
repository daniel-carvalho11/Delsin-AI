"""Configuração central do Delsin.

Todos os caminhos usam pathlib e seguem a especificação XDG do Linux
(~/.local/share, ~/.cache), com override por variáveis de ambiente.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "Delsin"
APP_VERSION = "0.4.0"

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _xdg_dir(env_var: str, fallback: Path) -> Path:
    value = os.environ.get(env_var)
    return Path(value).expanduser() if value else fallback


DATA_DIR = _xdg_dir("XDG_DATA_HOME", Path.home() / ".local" / "share") / "delsin"
CACHE_DIR = _xdg_dir("XDG_CACHE_HOME", Path.home() / ".cache") / "delsin"
LOG_DIR = DATA_DIR / "logs"
VOICES_DIR = DATA_DIR / "voices"
VOICE_PROFILE_PATH = DATA_DIR / "voice_profile.json"


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
    # Voz, tom, velocidade e volume ficam no perfil do usuário (config/voice_profile.py)
    tts_synthesis_timeout_s: float = 30.0
    voice_download_timeout_s: float = 300.0
    elevenlabs_model: str = "eleven_flash_v2_5"  # baixa latência, multilíngue (pt-BR)
    elevenlabs_timeout_s: float = 20.0
    tts_queue_size: int = 10


@dataclass(frozen=True)
class CoreSettings:
    skill_timeout_s: float = 10.0
    fallback_timeout_s: float = 200.0  # LLM na CPU: o primeiro carregamento do modelo é lento
    min_confidence: float = 0.5
    max_input_chars: int = 2000
    skill_workers: int = 4


@dataclass(frozen=True)
class LLMSettings:
    enabled: bool = True
    brain: str = "claude"               # "claude" (assinatura via Claude Code) | "ollama" (local)
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "low"          # conversa por voz: low responde mais rápido
    claude_timeout_s: float = 180.0
    base_url: str = "http://127.0.0.1:11434"  # Ollama local
    model: str = "qwen2.5:3b"
    temperature: float = 0.6
    context_tokens: int = 4096
    max_response_tokens: int = 320
    history_turns: int = 8              # pares pergunta/resposta mantidos como contexto
    request_timeout_s: float = 120.0
    keep_alive: str = "30m"             # tempo que o Ollama mantém o modelo na memória
    allow_remote: bool = False          # só aceita servidores em localhost


@dataclass(frozen=True)
class Settings:
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    core: CoreSettings = field(default_factory=CoreSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    debug: bool = False


def load_settings() -> Settings:
    env = os.environ
    lang = env.get("DELSIN_LANG")
    voice = VoiceSettings(language=lang) if lang else VoiceSettings()
    defaults = LLMSettings()
    llm = LLMSettings(
        enabled=env.get("DELSIN_LLM_DISABLED") != "1",
        brain=env.get("DELSIN_BRAIN", defaults.brain),
        claude_model=env.get("DELSIN_CLAUDE_MODEL", defaults.claude_model),
        claude_effort=env.get("DELSIN_CLAUDE_EFFORT", defaults.claude_effort),
        base_url=env.get("DELSIN_LLM_URL", defaults.base_url),
        model=env.get("DELSIN_LLM_MODEL", defaults.model),
        allow_remote=env.get("DELSIN_LLM_ALLOW_REMOTE") == "1",
    )
    return Settings(voice=voice, llm=llm, debug=env.get("DELSIN_DEBUG") == "1")


def ensure_dirs() -> None:
    """Cria diretórios de dados com permissão restrita ao usuário (0700)."""
    for directory in (DATA_DIR, CACHE_DIR, LOG_DIR, VOICES_DIR):
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o700)
