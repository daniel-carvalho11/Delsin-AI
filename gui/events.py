"""Eventos que as threads de trabalho enviam para a GUI via queue.Queue.

Única forma de outra thread "falar" com a interface: Tkinter não é
thread-safe e chamá-lo fora da main thread causa travamentos aleatórios.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModuleState(Enum):
    OFFLINE = "offline"
    STARTING = "iniciando"
    ONLINE = "online"
    ACTIVE = "ativo"
    ERROR = "erro"


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


UiEvent = StatusEvent | MessageEvent
