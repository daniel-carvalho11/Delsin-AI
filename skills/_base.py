"""Bases reutilizáveis para skills (não descobertas, prefixo "_")."""
from __future__ import annotations

import re
import unicodedata

from core.contracts import Request, Skill


def strip_accents(text: str) -> str:
    """Normaliza "horário" e "horario" para o mesmo termo — o STT varia."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


class KeywordSkill(Skill):
    """Skill acionada por palavras/expressões inteiras (sem acento, case-insensitive)."""

    keywords: tuple[str, ...] = ()

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if cls.keywords:
            alternatives = "|".join(re.escape(strip_accents(k.lower())) for k in cls.keywords)
            cls._pattern = re.compile(rf"\b(?:{alternatives})\b")

    def score(self, request: Request) -> float:
        pattern = getattr(self, "_pattern", None)
        if pattern is None:
            return 0.0
        return 0.9 if pattern.search(strip_accents(request.normalized)) else 0.0
