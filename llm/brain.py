"""Contrato comum dos "cérebros" (LLMs) do Delsin.

Um cérebro recebe texto e devolve texto + ações que ELE quis executar mas
foram bloqueadas pela política de permissões. O Delsin mostra essas ações
ao usuário, e só as executa após aprovação explícita.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class PendingAction:
    tool: str               # "Bash" | "Write" | "Edit" | ...
    input: dict[str, Any]   # parâmetros exatos que o modelo pediu
    summary: str            # frase curta para o cartão de confirmação


@dataclass(frozen=True, slots=True)
class BrainReply:
    text: str
    success: bool = True
    actions: tuple[PendingAction, ...] = ()
    meta: dict[str, Any] = field(default_factory=dict)


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

    def ask(self, text: str) -> BrainReply:
        """Uma rodada de conversa. Bloqueante; chamar fora da thread da GUI."""
        ...

    def reset(self) -> None:
        """Esquece o contexto da conversa."""
        ...

    def close(self) -> None:
        ...


def describe_action(tool: str, data: dict[str, Any]) -> str:
    """Resumo legível de uma ação bloqueada, para o cartão de confirmação."""
    if tool == "Bash":
        return f"Executar comando: {data.get('command', '')}"
    if tool == "Write":
        return f"Criar/substituir o arquivo {data.get('file_path', '?')} ({len(str(data.get('content', '')))} caracteres)"
    if tool == "Edit":
        return f"Editar o arquivo {data.get('file_path', '?')}"
    return f"Usar a ferramenta {tool}"
