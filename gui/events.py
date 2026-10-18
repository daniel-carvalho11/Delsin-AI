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
    stream_id: str = ""  # se houve streaming, substitui o bloco "ao vivo" com esse id


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
    tone: str = "info"  # "ok" | "warn" | "error" | "info"


@dataclass(frozen=True, slots=True)
class StreamEvent:
    """Texto parcial de uma resposta em andamento (acumulado, não só o pedaço novo)."""

    stream_id: str
    text: str


@dataclass(frozen=True, slots=True)
class IntegrationsEvent:
    active: tuple[str, ...]
    message: str = ""
    tone: str = "info"


@dataclass(frozen=True, slots=True)
class ActionRequestEvent:
    """O cérebro quer modificar algo no PC; o usuário precisa aprovar."""

    request_id: str
    items: tuple[str, ...]  # descrições exatas (comando, arquivo) mostradas no cartão


UiEvent = (StatusEvent | MessageEvent | ActivityEvent | MetricsEvent | VoiceCatalogEvent
           | ActionRequestEvent | StreamEvent | IntegrationsEvent)
