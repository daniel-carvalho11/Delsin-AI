"""Núcleo de roteamento do Delsin.

Fluxo:  Request -> validação -> Router.select() -> Skill.handle() (worker c/ timeout) -> Response

- O Agent não conhece GUI, voz nem skills concretas: só os contratos.
- O Router é uma estratégia trocável. Hoje: pontuação por palavras-chave.
  Amanhã: um LLMRouter que implementa o mesmo Protocol.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import replace
from typing import Protocol

from config.persona import DEFAULT_PERSONA, Persona
from config.settings import CoreSettings
from core.contracts import Request, Response, Skill, SkillContext, SkillInfo

log = logging.getLogger("delsin.core")


class Router(Protocol):
    def select(self, request: Request, skills: Iterable[Skill]) -> tuple[Skill, float] | None:
        """Retorna (skill, confiança) ou None se nenhuma atende."""
        ...


class ScoreRouter:
    """Escolhe a skill de maior score acima do limiar mínimo."""

    def __init__(self, min_confidence: float) -> None:
        self.min_confidence = min_confidence

    def select(self, request: Request, skills: Iterable[Skill]) -> tuple[Skill, float] | None:
        best: tuple[Skill, float] | None = None
        for skill in skills:
            try:
                score = float(skill.score(request))
            except Exception:
                log.exception("score() falhou na skill '%s' — ignorada", skill.name)
                continue
            if score >= self.min_confidence and (best is None or score > best[1]):
                best = (skill, score)
        return best


class Agent:
    def __init__(
        self,
        settings: CoreSettings,
        persona: Persona = DEFAULT_PERSONA,
        router: Router | None = None,
    ) -> None:
        self.settings = settings
        self.persona = persona
        self.router: Router = router or ScoreRouter(settings.min_confidence)
        self._skills: dict[str, Skill] = {}
        self._lock = threading.RLock()
        # Pools separados: o dispatcher espera pela skill; se dividissem o mesmo
        # pool, pedidos simultâneos poderiam esgotá-lo e travar (deadlock).
        self._dispatcher = ThreadPoolExecutor(max_workers=2, thread_name_prefix="delsin-dispatch")
        self._workers = ThreadPoolExecutor(
            max_workers=settings.skill_workers, thread_name_prefix="delsin-skill"
        )
        self._context = SkillContext(list_skills=self.list_skills, persona_name=persona.name)

    # ---------- registro de skills ----------

    def register(self, skill: Skill) -> bool:
        with self._lock:
            if skill.name in self._skills:
                log.warning("Skill duplicada '%s' ignorada", skill.name)
                return False
            try:
                skill.setup()
            except Exception:
                log.exception("setup() falhou na skill '%s' — não registrada", skill.name)
                return False
            self._skills[skill.name] = skill
        log.info("Skill registrada: %s", skill.name)
        return True

    def unregister(self, name: str) -> None:
        with self._lock:
            skill = self._skills.pop(name, None)
        if skill:
            self._safe_teardown(skill)

    def list_skills(self) -> list[SkillInfo]:
        with self._lock:
            return [s.info for s in self._skills.values()]

    # ---------- processamento ----------

    def handle(self, request: Request) -> Response:
        """Processa de forma síncrona. Não chame da thread da GUI — use submit()."""
        started = time.perf_counter()
        response = self._route(request)
        latency = (time.perf_counter() - started) * 1000
        log.info(
            "[%s] %s -> %s (%.0f ms)", request.id, request.source.value, response.skill, latency
        )
        return replace(response, latency_ms=latency)

    def submit(self, request: Request, callback: Callable[[Request, Response], None]) -> Future:
        """Processa em background e chama callback(request, response) no worker.

        O callback NÃO roda na thread da GUI: ele deve apenas enfileirar o resultado.
        """
        def run() -> None:
            response = self.handle(request)
            try:
                callback(request, response)
            except Exception:
                log.exception("Callback de resposta falhou")

        return self._dispatcher.submit(run)

    def _route(self, request: Request) -> Response:
        text = request.text.strip()
        if not text:
            return Response(self.persona.empty_input, "core", success=False, speak=False)
        if len(text) > self.settings.max_input_chars:
            msg = self.persona.too_long.format(limit=self.settings.max_input_chars)
            return Response(msg, "core", success=False)

        with self._lock:
            skills = list(self._skills.values())
        match = self.router.select(request, skills)
        if match is None:
            return Response(self.persona.fallback, "fallback", success=False)

        skill, score = match
        log.debug("[%s] roteado para '%s' (score %.2f)", request.id, skill.name, score)
        future = self._workers.submit(skill.handle, request, self._context)
        try:
            return future.result(timeout=self.settings.skill_timeout_s)
        except FutureTimeout:
            # Limitação do Python: threads não podem ser mortas. A skill continua
            # rodando em segundo plano até terminar; só abandonamos o resultado.
            future.cancel()
            log.warning("[%s] timeout na skill '%s'", request.id, skill.name)
            msg = self.persona.timeout.format(
                skill=skill.name, seconds=self.settings.skill_timeout_s
            )
            return Response(msg, skill.name, success=False)
        except Exception:
            log.exception("[%s] erro na skill '%s'", request.id, skill.name)
            return Response(self.persona.failure.format(skill=skill.name), skill.name, success=False)

    # ---------- ciclo de vida ----------

    def shutdown(self) -> None:
        self._dispatcher.shutdown(wait=False, cancel_futures=True)
        self._workers.shutdown(wait=False, cancel_futures=True)
        with self._lock:
            skills, self._skills = list(self._skills.values()), {}
        for skill in skills:
            self._safe_teardown(skill)
        log.info("Core desligado")

    @staticmethod
    def _safe_teardown(skill: Skill) -> None:
        try:
            skill.teardown()
        except Exception:
            log.exception("teardown() falhou na skill '%s'", skill.name)
