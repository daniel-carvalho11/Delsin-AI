"""Contratos estáveis entre o Core e os módulos.

Skills, routers e front-ends (GUI, voz, futura API) dependem apenas deste
arquivo — nunca uns dos outros. É isso que permite extrair um agente
especialista levando só o Core + as skills dele.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Source(str, Enum):
    TEXT = "text"
    VOICE = "voice"


@dataclass(frozen=True, slots=True)
class Request:
    text: str
    source: Source = Source.TEXT
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def normalized(self) -> str:
        return " ".join(self.text.lower().split())


@dataclass(frozen=True, slots=True)
class Response:
    text: str
    skill: str
    success: bool = True
    speak: bool = True
    latency_ms: float = 0.0
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SkillInfo:
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class SkillContext:
    """O que uma skill pode enxergar do agente — e nada além disso."""

    list_skills: Callable[[], list[SkillInfo]]
    persona_name: str


class Skill(ABC):
    """Unidade de capacidade plugável.

    score() deve ser barato (roda para toda skill a cada comando);
    handle() pode ser lento — roda num worker com timeout.
    """

    name: str = "unnamed"
    description: str = ""

    @abstractmethod
    def score(self, request: Request) -> float:
        """Confiança entre 0.0 e 1.0 de que esta skill atende ao pedido."""

    @abstractmethod
    def handle(self, request: Request, context: SkillContext) -> Response:
        """Executa o pedido. Exceções são capturadas pelo Core."""

    def setup(self) -> None:
        """Aquisição de recursos (conexões, modelos). Chamado no registro."""

    def teardown(self) -> None:
        """Liberação de recursos. Chamado no desligamento."""

    @property
    def info(self) -> SkillInfo:
        return SkillInfo(self.name, self.description)
