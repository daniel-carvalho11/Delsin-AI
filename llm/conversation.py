"""Conversa livre com o cérebro (Claude via Claude Code, ou Ollama local).

Usada como FALLBACK do Agent: as skills de palavra-chave respondem primeiro
(instantâneas); só o que nenhuma skill reconhece chega aqui.

Também é registrada como skill comum para reconhecer "nova conversa"
(apagar o contexto).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from config.persona import Persona
from core.contracts import Request, Response, Skill, SkillContext
from llm.brain import Brain, PendingAction

log = logging.getLogger("delsin.llm")

_WEEKDAYS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
             "sexta-feira", "sábado", "domingo")
_RESET = re.compile(r"\b(nova conversa|limpar contexto|apagar contexto|esque[cç]a a conversa|reiniciar conversa)\b")
# Modelos de raciocínio (ex.: qwen3, deepseek-r1) devolvem o "pensamento" entre <think>.
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_MARKDOWN = re.compile(r"(\*\*|__|`|^#+\s*)", re.MULTILINE)


def clean_reply(text: str) -> str:
    text = _THINK.sub("", text)
    text = _MARKDOWN.sub("", text)
    return text.strip()


def now_tag() -> str:
    now = datetime.now()
    return f"[{_WEEKDAYS[now.weekday()]}, {now:%d/%m/%Y %H:%M}]"


class ConversationSkill(Skill):
    name = "llm"
    description = "Conversa livre com a IA. Diga 'nova conversa' para apagar o contexto."

    def __init__(self, brain: Brain, persona: Persona) -> None:
        self.brain = brain
        self._persona = persona

    @property
    def model(self) -> str:
        return self.brain.model

    def check(self) -> tuple[bool, str]:
        return self.brain.check()

    def start(self, context: SkillContext) -> None:
        """Abre a sessão do cérebro com o prompt de sistema (persona + capacidades)."""
        skills = ", ".join(f"{s.name} ({s.description})" for s in context.list_skills() if s.name != self.name)
        self.brain.start(
            f"{self._persona.system_prompt}\n{self._persona.voice_rules}\n"
            f"{self._persona.capabilities(self.brain.name)}\n"
            f"Comandos locais que o usuário também pode usar: {skills}.\n"
            "Cada mensagem do usuário começa com a data e hora atuais entre colchetes."
        )

    def teardown(self) -> None:
        self.brain.close()

    def score(self, request: Request) -> float:
        return 0.95 if _RESET.search(request.normalized) else 0.0

    def handle(self, request: Request, context: SkillContext) -> Response:
        if _RESET.search(request.normalized):
            self.brain.reset()
            return Response(self._persona.llm_reset, self.name)
        return self._ask(f"{now_tag()} {request.text}")

    def follow_up(self, note: str) -> Response:
        """Mensagem do próprio Delsin para o cérebro (ex.: resultado de uma ação aprovada)."""
        return self._ask(f"{now_tag()} [mensagem do sistema Delsin, não do usuário] {note}")

    def _ask(self, text: str) -> Response:
        reply = self.brain.ask(text)
        if not reply.success:
            log.warning("Cérebro %s falhou: %s", self.brain.name, reply.text)
            return Response(self._persona.llm_offline.format(reason=reply.text), self.name,
                            success=False, data=reply.meta)
        answer = clean_reply(reply.text) or ("Preciso da sua confirmação no painel." if reply.actions
                                             else "Não consegui formular uma resposta.")
        log.info("Cérebro %s respondeu (%s ms%s)", self.brain.name, reply.meta.get("duration_ms", "?"),
                 f", {len(reply.actions)} ação(ões) aguardando aprovação" if reply.actions else "")
        return Response(answer, self.name, data={**reply.meta, "actions": reply.actions})


def actions_of(response: Response) -> tuple[PendingAction, ...]:
    return tuple(response.data.get("actions") or ())
