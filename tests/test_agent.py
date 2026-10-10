"""Testes do Core sem GUI nem áudio:  python -m unittest discover -s tests"""
from __future__ import annotations

import time
import unittest

from config.settings import CoreSettings
from core import Agent, Request, Response, Skill, SkillContext
from skills import discover_skills


class _SlowSkill(Skill):
    name = "slow"

    def score(self, request: Request) -> float:
        return 1.0 if "devagar" in request.normalized else 0.0

    def handle(self, request: Request, context: SkillContext) -> Response:
        time.sleep(1)
        return Response("terminei", self.name)


class _BrokenSkill(Skill):
    name = "broken"

    def score(self, request: Request) -> float:
        return 1.0 if "quebra" in request.normalized else 0.0

    def handle(self, request: Request, context: SkillContext) -> Response:
        raise RuntimeError("boom")


class AgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.agent = Agent(CoreSettings(skill_timeout_s=0.3))
        for skill in [*discover_skills(), _SlowSkill(), _BrokenSkill()]:
            self.agent.register(skill)

    def tearDown(self) -> None:
        self.agent.shutdown()

    def test_routes_to_clock_ignoring_accents(self) -> None:
        self.assertEqual(self.agent.handle(Request("Que HORÁRIO é agora?")).skill, "clock")

    def test_fallback_when_no_skill_matches(self) -> None:
        response = self.agent.handle(Request("pilote um drone"))
        self.assertEqual(response.skill, "fallback")
        self.assertFalse(response.success)

    def test_timeout_is_contained(self) -> None:
        response = self.agent.handle(Request("vai devagar"))
        self.assertFalse(response.success)
        self.assertLess(response.latency_ms, 900)

    def test_skill_exception_is_contained(self) -> None:
        self.assertFalse(self.agent.handle(Request("quebra tudo")).success)

    def test_rejects_oversized_input(self) -> None:
        self.assertFalse(self.agent.handle(Request("x" * 5000)).success)

    def test_duplicate_registration_rejected(self) -> None:
        self.assertFalse(self.agent.register(_SlowSkill()))


if __name__ == "__main__":
    unittest.main()
