"""Testes de perfil de voz e motores (sem tocar áudio)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from config.settings import VoiceSettings
from config.voice_profile import PITCH_RANGE, VoiceProfile, load_profile, save_profile
from voice.engines import EspeakEngine, PiperEngine, SynthesisError
from voice.tts import TextToSpeech


class VoiceProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "voice_profile.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_roundtrip(self) -> None:
        profile = VoiceProfile("espeak", "pt-br+f2", rate=1.2, pitch=1.1, volume=0.8)
        save_profile(profile, self.path)
        self.assertEqual(load_profile(self.path), profile)

    def test_missing_file_returns_default(self) -> None:
        self.assertEqual(load_profile(self.path), VoiceProfile())

    def test_corrupted_file_returns_default(self) -> None:
        self.path.write_text("{ não é json")
        self.assertEqual(load_profile(self.path), VoiceProfile())

    def test_values_are_clamped_and_unknown_keys_ignored(self) -> None:
        self.path.write_text(json.dumps({"engine": "hack", "pitch": 9, "rate": -3, "extra": 1}))
        profile = load_profile(self.path)
        self.assertEqual(profile.engine, "espeak")
        self.assertEqual(profile.pitch, PITCH_RANGE[1])
        self.assertGreater(profile.rate, 0)


    def test_input_device_name_is_validated(self) -> None:
        good = "alsa_input.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__Mic1__source"
        self.assertEqual(VoiceProfile(input_device=good).clamped().input_device, good)
        self.assertEqual(VoiceProfile(input_device="x; rm -rf ~").clamped().input_device, "")


class EngineTest(unittest.TestCase):
    def test_piper_rejects_path_traversal(self) -> None:
        engine = PiperEngine(Path(tempfile.gettempdir()), 1)
        with self.assertRaises(SynthesisError):
            engine.synthesize("x", VoiceProfile(voice="../../etc/passwd"))

    def test_piper_install_only_from_catalog(self) -> None:
        engine = PiperEngine(Path(tempfile.gettempdir()), 1)
        with self.assertRaises(SynthesisError):
            engine.install("en_US-qualquer-medium")

    @unittest.skipUnless(EspeakEngine(5).check()[0], "espeak-ng não instalado")
    def test_espeak_pitch_changes_audio(self) -> None:
        engine = EspeakEngine(5)
        low = engine.synthesize("teste", VoiceProfile("espeak", "pt-br", pitch=0.8))
        high = engine.synthesize("teste", VoiceProfile("espeak", "pt-br", pitch=1.3))
        self.assertGreater(len(low.pcm), 0)
        self.assertNotEqual(low.pcm, high.pcm)


class TextToSpeechTest(unittest.TestCase):
    def test_preview_signature_matches_dialog_callback(self) -> None:
        # Regressão: a janela chama on_preview(perfil, texto).
        tts = TextToSpeech(VoiceSettings(), VoiceProfile(), Path(tempfile.gettempdir()))
        tts.preview(VoiceProfile("espeak", "pt-br"), "teste")  # não inicializado: não toca, mas não pode quebrar

    def test_falls_back_to_espeak_when_voice_missing(self) -> None:
        with tempfile.TemporaryDirectory() as empty_dir:
            tts = TextToSpeech(VoiceSettings(), VoiceProfile("piper", "pt_BR-cadu-medium"), Path(empty_dir))
            ok, _ = tts.initialize()
            try:
                if not ok:
                    self.skipTest("sem player/motor de áudio neste ambiente")
                self.assertEqual(tts.profile.engine, "espeak")
                catalog = tts.catalog()
                self.assertIn("espeak", catalog.voices)
            finally:
                tts.shutdown()


if __name__ == "__main__":
    unittest.main()
