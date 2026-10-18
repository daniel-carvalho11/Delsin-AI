"""Fatia texto em frases à medida que ele chega (streaming → voz).

A primeira frase sai assim que fecha (ponto, interrogação...), então o Delsin
começa a falar enquanto o resto da resposta ainda está sendo gerado.
"""
from __future__ import annotations

import re

_BOUNDARY = re.compile(r"(?<=[.!?…:;])\s+|\n+")
_MARKUP = re.compile(r"(\*\*|__|`+|^#+\s*|^\s*[-*•]\s+)", re.MULTILINE)


def speakable(text: str) -> str:
    """Remove marcações que soariam estranhas em voz alta."""
    return " ".join(_MARKUP.sub("", text).split())


class SentenceChunker:
    def __init__(self, min_chars: int = 24) -> None:
        self._buffer = ""
        self._min_chars = min_chars

    def feed(self, text: str) -> list[str]:
        self._buffer += text
        sentences = []
        while True:
            cut = next((m for m in _BOUNDARY.finditer(self._buffer) if m.start() >= self._min_chars), None)
            if cut is None:
                break
            sentences.append(self._buffer[:cut.start()])
            self._buffer = self._buffer[cut.end():]
        return [s for s in map(speakable, sentences) if s]

    def flush(self) -> list[str]:
        rest, self._buffer = speakable(self._buffer), ""
        return [rest] if rest else []
