"""Testes dos cérebros (Claude Code e Ollama) sem rede externa e sem gastar cota.

- Claude Code: um executável falso (tests/fake_claude.py) fala o mesmo stream-json.
- Ollama: um servidor HTTP falso local.
"""
from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from config.persona import DEFAULT_PERSONA
from config.settings import CoreSettings
from core import Agent, Request
from llm import ClaudeCodeBrain, ConversationSkill, OllamaBrain, OllamaClient
from llm.claude_code import allowed_rules, denied_rules
from llm.conversation import clean_reply

FAKE_CLAUDE = Path(__file__).with_name("fake_claude.py")


def make_fake_claude(directory: Path) -> str:
    script = directory / "claude"
    script.write_text(f"#!{sys.executable}\n" + FAKE_CLAUDE.read_text(encoding="utf-8"), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


class ClaudeCodeBrainTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.brain = ClaudeCodeBrain("claude-opus-5-5", "low", 5, tmp, binary=make_fake_claude(tmp))
        self.skill = ConversationSkill(self.brain, DEFAULT_PERSONA)
        self.agent = Agent(CoreSettings())
        self.agent.register(self.skill)
        self.agent.set_fallback(self.skill)
        self.skill.start(self.agent.context)

    def tearDown(self) -> None:
        self.agent.shutdown()
        self._tmp.cleanup()

    def test_check_accepts_subscription_login(self) -> None:
        ok, detail = self.brain.check()
        self.assertTrue(ok, detail)
        self.assertIn("assinatura", detail)

    def test_context_persists_in_one_process(self) -> None:
        first = self.agent.handle(Request("olá"))
        second = self.agent.handle(Request("tudo bem?"))
        self.assertEqual(first.skill, "llm")
        self.assertIn("eco 1:", first.text)
        self.assertIn("eco 2:", second.text)  # mesmo processo = mesma conversa

    def test_approval_is_asked_in_real_time(self) -> None:
        asked = []
        self.brain.approver = lambda action: asked.append(action) or True
        self.assertEqual(self.agent.handle(Request("crie o arquivo com touch")).text, "Arquivo criado.")
        self.assertEqual(asked[0].input["command"], "touch /tmp/x")
        self.assertIn("touch /tmp/x", asked[0].summary)

    def test_denial_and_missing_approver_refuse(self) -> None:
        self.brain.approver = lambda action: False
        self.assertEqual(self.agent.handle(Request("touch de novo")).text, "Ok, não criei.")
        self.brain.approver = None  # sem aprovador: sempre nega
        self.assertEqual(self.agent.handle(Request("touch mais uma")).text, "Ok, não criei.")

    def test_streaming_deltas_reach_listener(self) -> None:
        chunks = []
        self.skill.on_stream = lambda request_id, delta: chunks.append(delta)
        response = self.agent.handle(Request("olá"))
        self.assertEqual("".join(chunks), "eco 1: " + response.text.split(": ", 1)[1])
        self.assertTrue(response.data["streamed"])

    def test_reset_starts_new_process(self) -> None:
        self.agent.handle(Request("olá"))
        self.agent.handle(Request("nova conversa"))
        self.assertIn("eco 1:", self.agent.handle(Request("de novo")).text)

    def test_recovers_after_process_dies(self) -> None:
        dead = self.agent.handle(Request("morra"))
        self.assertFalse(dead.success)
        self.assertIn("eco 1:", self.agent.handle(Request("voltou?")).text)

    def test_timeout_restarts_session(self) -> None:
        self.brain._timeout_s = 0.5
        hung = self.brain.ask("trave")
        self.assertFalse(hung.success)
        self.brain._timeout_s = 5
        self.assertIn("eco 1:", self.brain.ask("ok?").text)

    def test_api_key_is_not_forwarded(self) -> None:
        os.environ["ANTHROPIC_API_KEY"] = "sk-teste"
        try:
            self.assertNotIn("ANTHROPIC_API_KEY", self.brain._env())
        finally:
            del os.environ["ANTHROPIC_API_KEY"]

    def test_permission_rules(self) -> None:
        self.assertIn("Bash(df *)", allowed_rules())
        self.assertNotIn("Bash", allowed_rules())  # Bash livre nunca é liberado
        self.assertIn("Read(~/.ssh/**)", denied_rules())
        command = self.brain._command()
        self.assertIn("stdio", command)       # aprovação vem para o Delsin
        self.assertIn("manual", command)
        self.assertIn("--strict-mcp-config", command)
        self.assertEqual(command[command.index("--setting-sources") + 1], "")
        self.assertNotIn("--dangerously-skip-permissions", command)


class _FakeOllama(BaseHTTPRequestHandler):
    chats: list[dict] = []

    def log_message(self, *_args) -> None:
        pass

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/version":
            self._send({"version": "0.0-test"})
        elif self.path == "/api/tags":
            self._send({"models": [{"name": "qwen2.5:3b"}]})
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self) -> None:
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/generate":
            self._send({"done": True})
        elif self.path == "/api/chat":
            _FakeOllama.chats.append(payload)
            self._send({"model": payload["model"], "done": True, "eval_count": 12, "eval_duration": 10**9,
                        "message": {"role": "assistant",
                                    "content": f"<think>x</think>**Resposta {len(_FakeOllama.chats)}**"}})


class OllamaBrainTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeOllama)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()

    def _brain(self, model: str = "qwen2.5:3b", url: str | None = None) -> OllamaBrain:
        return OllamaBrain(OllamaClient(url or self.url, 5), model, temperature=0.6, context_tokens=4096,
                           max_response_tokens=100, history_turns=2, keep_alive="1m")

    def setUp(self) -> None:
        _FakeOllama.chats.clear()
        self.skill = ConversationSkill(self._brain(), DEFAULT_PERSONA)
        self.agent = Agent(CoreSettings())
        self.agent.register(self.skill)
        self.agent.set_fallback(self.skill)
        self.skill.start(self.agent.context)

    def tearDown(self) -> None:
        self.agent.shutdown()

    def test_missing_model_is_reported(self) -> None:
        ok, detail = self._brain("llama9:70b").check()
        self.assertFalse(ok)
        self.assertIn("ollama pull llama9:70b", detail)

    def test_reply_is_cleaned_and_prompt_is_local(self) -> None:
        response = self.agent.handle(Request("olá, tudo bem?"))
        self.assertEqual(response.text, "Resposta 1")
        system = _FakeOllama.chats[0]["messages"][0]["content"]
        self.assertIn("português do Brasil", system)
        self.assertIn("sem acesso à internet", system)

    def test_history_is_bounded_and_reset(self) -> None:
        for text in ("um", "dois", "três"):
            self.agent.handle(Request(text))
        self.assertEqual(len(_FakeOllama.chats[-1]["messages"]), 6)  # system + 2 turnos + atual
        self.agent.handle(Request("nova conversa"))
        self.agent.handle(Request("quatro"))
        self.assertEqual(len(_FakeOllama.chats[-1]["messages"]), 2)

    def test_offline_server_gives_friendly_failure(self) -> None:
        skill = ConversationSkill(self._brain(url="http://127.0.0.1:9"), DEFAULT_PERSONA)
        response = skill.handle(Request("teste"), self.agent.context)
        self.assertFalse(response.success)
        self.assertIn("IA local está indisponível", response.text)

    def test_remote_server_blocked_by_default(self) -> None:
        with self.assertRaises(ValueError):
            OllamaClient("http://192.168.0.10:11434", 5)

    def test_keyword_skills_still_win(self) -> None:
        from skills.builtin import ClockSkill

        self.agent.register(ClockSkill())
        self.assertEqual(self.agent.handle(Request("que horas são?")).skill, "clock")
        self.assertEqual(_FakeOllama.chats, [])


class CleanReplyTest(unittest.TestCase):
    def test_strips_think_and_markdown(self) -> None:
        self.assertEqual(clean_reply("<think>\nplano\n</think>\n## Olá **mundo**"), "Olá mundo")


if __name__ == "__main__":
    unittest.main()
