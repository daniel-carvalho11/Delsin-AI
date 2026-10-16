"""Testes do executor de ações aprovadas, dos segredos e do motor ElevenLabs (servidor falso)."""
from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from config.secrets import get_secret, mask, set_secret
from config.voice_profile import VoiceProfile
from services.actions import ActionRunner
from voice import engines
from voice.engines import ElevenLabsEngine, SynthesisError


class ActionRunnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.runner = ActionRunner(self.home, timeout_s=3)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_bash_runs_in_home_and_captures_output(self) -> None:
        result = self.runner.run("Bash", {"command": "pwd; echo oi"})
        self.assertTrue(result.ok)
        self.assertIn(str(self.home.resolve()), result.output)
        self.assertIn("oi", result.output)

    def test_background_program_does_not_block(self) -> None:
        started = time.monotonic()
        result = self.runner.run("Bash", {"command": "sleep 30 &"})
        self.assertTrue(result.ok)
        self.assertLess(time.monotonic() - started, 2)

    def test_timeout_kills_command(self) -> None:
        result = self.runner.run("Bash", {"command": "sleep 30"})
        self.assertFalse(result.ok)
        self.assertIn("excedeu", result.output)

    def test_write_and_edit_inside_home(self) -> None:
        self.assertTrue(self.runner.run("Write", {"file_path": str(self.home / "a/b.txt"), "content": "x=1"}).ok)
        self.assertTrue(self.runner.run("Edit", {"file_path": str(self.home / "a/b.txt"),
                                                 "old_string": "x=1", "new_string": "x=2"}).ok)
        self.assertEqual((self.home / "a/b.txt").read_text(), "x=2")

    def test_write_outside_home_is_refused(self) -> None:
        result = self.runner.run("Write", {"file_path": "/etc/delsin_teste", "content": "x"})
        self.assertFalse(result.ok)
        result = self.runner.run("Write", {"file_path": str(self.home / "../fora.txt"), "content": "x"})
        self.assertFalse(result.ok)

    def test_unknown_tool_is_refused(self) -> None:
        self.assertFalse(self.runner.run("WebFetch", {"url": "x"}).ok)


class SecretsTest(unittest.TestCase):
    def test_roundtrip_permissions_and_env_precedence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delsin" / "secrets.env"
            set_secret("ELEVENLABS_API_KEY", "abc123456789xyz", path)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertEqual(get_secret("ELEVENLABS_API_KEY", path), "abc123456789xyz")
            os.environ["ELEVENLABS_API_KEY"] = "do-ambiente"
            try:
                self.assertEqual(get_secret("ELEVENLABS_API_KEY", path), "do-ambiente")
            finally:
                del os.environ["ELEVENLABS_API_KEY"]
            with self.assertRaises(ValueError):
                set_secret("X", "a\nINJECAO=1", path)
        self.assertEqual(mask("abc123456789xyz"), "abc1…9xyz")


class _FakeEleven(BaseHTTPRequestHandler):
    last_body: dict = {}

    def log_message(self, *_args) -> None:
        pass

    def _reply(self, status: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.headers.get("xi-api-key") != "boa":
            self._reply(401, b'{"detail":"invalid"}')
            return
        voices = {"voices": [{"voice_id": "AbCdEfGhIjKlMnOpQrSt", "name": "Ana",
                              "labels": {"gender": "female", "accent": "brazilian"}}]}
        self._reply(200, json.dumps(voices).encode())

    def do_POST(self) -> None:
        _FakeEleven.last_body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.headers.get("xi-api-key") != "boa":
            self._reply(401, b'{"detail":"invalid"}')
            return
        self._reply(200, b"\x10\x00" * 2205, "audio/pcm")  # 0,1 s de PCM


class ElevenLabsEngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeEleven)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls._original_url = engines.ELEVENLABS_URL
        engines.ELEVENLABS_URL = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        engines.ELEVENLABS_URL = cls._original_url
        cls.server.shutdown()

    def test_voices_and_synthesis(self) -> None:
        engine = ElevenLabsEngine(lambda: "boa", "eleven_flash_v2_5", 5)
        ok, detail = engine.check()
        self.assertTrue(ok, detail)
        self.assertEqual(engine.voices()[0].label, "Ana · female brazilian")
        clip = engine.synthesize("Olá", VoiceProfile("elevenlabs", "AbCdEfGhIjKlMnOpQrSt", pitch=1.1, rate=1.0))
        self.assertEqual(clip.sample_rate, round(22050 * 1.1))
        self.assertEqual(len(clip.pcm), 4410)
        self.assertEqual(_FakeEleven.last_body["language_code"], "pt")
        self.assertAlmostEqual(_FakeEleven.last_body["voice_settings"]["speed"], 0.91, places=2)

    def test_bad_key_and_missing_key(self) -> None:
        self.assertFalse(ElevenLabsEngine(lambda: "ruim", "eleven_flash_v2_5", 5).check()[0])
        self.assertIn("não configurada", ElevenLabsEngine(lambda: None, "m", 5).check()[1])

    def test_voice_id_is_validated(self) -> None:
        engine = ElevenLabsEngine(lambda: "boa", "eleven_flash_v2_5", 5)
        with self.assertRaises(SynthesisError):
            engine.synthesize("x", VoiceProfile("elevenlabs", "../../v1/user"))


if __name__ == "__main__":
    unittest.main()
