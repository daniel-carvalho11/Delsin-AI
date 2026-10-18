"""Contrato comum dos "cérebros" (LLMs) do Delsin.

Um cérebro recebe texto e devolve texto. Durante a resposta ele pode:
- emitir pedaços do texto (streaming), para a GUI e a voz começarem antes do fim;
- pedir aprovação para uma ação (comando, arquivo, e-mail...). O Delsin mostra
  o pedido exato ao usuário e devolve sim/não; nada roda sem o "sim".
"""
from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class PendingAction:
    tool: str               # "Bash", "Write", "mcp__gmail__send_email"...
    input: dict[str, Any]   # parâmetros exatos que o modelo pediu
    summary: str            # texto mostrado no cartão de aprovação


@dataclass(frozen=True, slots=True)
class BrainReply:
    text: str
    success: bool = True
    streamed: bool = False
    meta: dict[str, Any] = field(default_factory=dict)


DeltaCallback = Callable[[str], None]
Approver = Callable[[PendingAction], bool]


class Brain(Protocol):
    name: str
    label: str
    model: str

    def check(self) -> tuple[bool, str]:
        """Disponibilidade (servidor, login, modelo). Não levanta exceção."""
        ...

    def start(self, system_prompt: str) -> None:
        """Prepara o cérebro (carrega modelo / abre sessão). Pode ser lento."""
        ...

    def ask(self, text: str, on_delta: DeltaCallback | None = None) -> BrainReply:
        """Uma rodada de conversa. Bloqueante; chamar fora da thread da GUI."""
        ...

    def reset(self) -> None:
        """Esquece o contexto da conversa."""
        ...

    def close(self) -> None:
        ...


def describe_action(tool: str, data: dict[str, Any]) -> str:
    """Resumo legível e COMPLETO o bastante para o usuário decidir."""
    if tool == "Bash":
        return f"Executar comando: {data.get('command', '')}"
    if tool == "Write":
        return f"Criar/substituir o arquivo {data.get('file_path', '?')} ({len(str(data.get('content', '')))} caracteres)"
    if tool == "Edit":
        return f"Editar o arquivo {data.get('file_path', '?')}: trocar {str(data.get('old_string', ''))[:60]!r}"
    if tool.startswith("mcp__"):
        _, server, name = (tool.split("__", 2) + ["", ""])[:3]
        params = ", ".join(f"{k}={json.dumps(v, ensure_ascii=False)[:120]}" for k, v in data.items())
        return f"{server}: {name}({params})"
    return f"Usar {tool}: {json.dumps(data, ensure_ascii=False)[:200]}"
