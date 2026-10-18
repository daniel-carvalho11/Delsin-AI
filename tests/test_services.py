"""Testes dos segredos e do motor ElevenLabs (servidor falso)."""
from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from config.secrets import get_secret, mask, set_secret
from config.voice_profile import VoiceProfile
from voice import engines
from voice.engines import ElevenLabsEngine, SynthesisError


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
        self.assertEqual(engine.voices()[0].label, "Ana · feminina · sotaque brazilian")
        clip = engine.synthesize("Olá", VoiceProfile("elevenlabs", "AbCdEfGhIjKlMnOpQrSt", pitch=1.1, rate=1.0,
                                                    cloud_model="eleven_flash_v2_5"))
        self.assertEqual(clip.sample_rate, round(22050 * 1.1))
        self.assertEqual(len(clip.pcm), 4410)
        self.assertEqual(_FakeEleven.last_body["language_code"], "pt")
        self.assertAlmostEqual(_FakeEleven.last_body["voice_settings"]["speed"], 0.91, places=2)

    def test_bad_key_and_missing_key(self) -> None:
        self.assertFalse(ElevenLabsEngine(lambda: "ruim", "eleven_flash_v2_5", 5).check()[0])
        self.assertIn("não configurada", ElevenLabsEngine(lambda: None, "m", 5).check()[1])

    def test_brazilian_voices_listed_first_and_model_from_profile(self) -> None:
        voices = {"voices": [
            {"voice_id": "AAAAAAAAAAAAAAAAAAAA", "name": "Adam - Firm", "labels": {"gender": "male", "accent": "american"}},
            {"voice_id": "ZZZZZZZZZZZZZZZZZZZZ", "name": "Will - Relaxed", "labels": {"gender": "male"},
             "verified_languages": [{"language": "pt", "locale": "pt-BR"}]},
        ]}
        engine = ElevenLabsEngine(lambda: "boa", "eleven_flash_v2_5", 5)
        engine._request = lambda *_a, **_k: json.dumps(voices).encode()
        labels = [o.label for o in engine.voices()]
        self.assertEqual(labels[0], "Will · masculina · pt-BR verificada")
        self.assertEqual(labels[1], "Adam · masculina · sotaque american")
        self.assertEqual(VoiceProfile(cloud_model="inventado").clamped().cloud_model, "eleven_multilingual_v2")

    def test_api_error_messages_are_explained(self) -> None:
        from voice.engines import _eleven_error

        body = '{"detail": {"status": "payment_required", "message": "Free users cannot use library voices via the API."}}'
        self.assertIn("Voice Library exige plano pago", _eleven_error(402, body))
        body = '{"detail": {"status": "quota_exceeded", "message": "This request exceeds your quota."}}'
        self.assertIn("créditos do mês esgotados", _eleven_error(401, body))

    def test_voice_id_is_validated(self) -> None:
        engine = ElevenLabsEngine(lambda: "boa", "eleven_flash_v2_5", 5)
        with self.assertRaises(SynthesisError):
            engine.synthesize("x", VoiceProfile("elevenlabs", "../../v1/user"))


if __name__ == "__main__":
    unittest.main()


class IntegrationsTest(unittest.TestCase):
    def test_read_only_policy(self) -> None:
        from services.integrations import is_read_only

        for tool in ("mcp__notion__API-post-search", "mcp__notion__API-retrieve-a-page",
                     "mcp__gmail__search_gmail_messages"):
            self.assertTrue(is_read_only(tool), tool)
        for tool in ("mcp__notion__API-post-page", "mcp__notion__API-delete-a-block",
                     "mcp__gmail__send_gmail_message", "mcp__gmail__draft_gmail_message", "Bash", "Write"):
            self.assertFalse(is_read_only(tool), tool)

    def test_mcp_config_generated_from_secrets_with_private_permissions(self) -> None:
        from services.integrations import write_mcp_config

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "delsin" / "mcp.json"
            self.assertEqual(write_mcp_config(path, lambda name: None), [])
            active = write_mcp_config(path, lambda name: "ntn_x" if name == "NOTION_TOKEN" else None)
            self.assertEqual(active, ["notion"])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            config = json.loads(path.read_text())
            self.assertEqual(config["mcpServers"]["notion"]["env"]["NOTION_TOKEN"], "ntn_x")
