"""Eventos que as threads de trabalho enviam para a GUI via queue.Queue.

Única forma de outra thread "falar" com a interface: Tkinter não é
thread-safe e chamá-lo fora da main thread causa travamentos aleatórios.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from config.voice_profile import VoiceCatalog


class ModuleState(Enum):
    OFFLINE = "offline"
    STARTING = "iniciando"
    ONLINE = "online"
    ACTIVE = "ativo"
    ERROR = "erro"


class Activity(Enum):
    """Estado do assistente, mostrado no painel Neural Trace."""

    IDLE = "ocioso"
    LISTENING = "ouvindo"
    PROCESSING = "processando"
    SPEAKING = "falando"


@dataclass(frozen=True, slots=True)
class StatusEvent:
    module: str
    state: ModuleState
    detail: str = ""


@dataclass(frozen=True, slots=True)
class MessageEvent:
    author: str  # "user" | "delsin" | "system"
    text: str
    meta: str = ""
    failed: bool = False
    latency_ms: float | None = None


@dataclass(frozen=True, slots=True)
class ActivityEvent:
    activity: Activity


@dataclass(frozen=True, slots=True)
class MetricView:
    key: str
    label: str
    fraction: float
    display: str


@dataclass(frozen=True, slots=True)
class MetricsEvent:
    metrics: tuple[MetricView, ...]


@dataclass(frozen=True, slots=True)
class VoiceCatalogEvent:
    catalog: VoiceCatalog
    message: str = ""


UiEvent = StatusEvent | MessageEvent | ActivityEvent | MetricsEvent | VoiceCatalogEvent
