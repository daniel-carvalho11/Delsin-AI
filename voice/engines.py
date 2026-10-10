"""Motores de síntese de voz.

Cada motor apenas GERA áudio (PCM 16-bit mono); quem toca é o PcmPlayer.
Isso permite trocar o motor sem mexer na reprodução e interromper a fala
matando um único processo.
"""
from __future__ import annotations

import io
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from config.voice_profile import VoiceOption, VoiceProfile

log = logging.getLogger("delsin.voice.engines")


class SynthesisError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class AudioClip:
    pcm: bytes
    sample_rate: int

    @property
    def duration_s(self) -> float:
        return len(self.pcm) / 2 / self.sample_rate


class Engine(Protocol):
    name: str
    label: str

    def check(self) -> tuple[bool, str]: ...
    def voices(self) -> list[VoiceOption]: ...
    def synthesize(self, text: str, profile: VoiceProfile) -> AudioClip: ...


# ---------------------------------------------------------------- espeak-ng

ESPEAK_VOICES = (
    ("pt-br", "Padrão"),
    ("pt-br+m1", "Masculina 1"),
    ("pt-br+m3", "Masculina 3 (grave)"),
    ("pt-br+m7", "Masculina 7"),
    ("pt-br+Henrique", "Henrique"),
    ("pt-br+marcelo", "Marcelo"),
    ("pt-br+Diogo", "Diogo"),
    ("pt-br+f1", "Feminina 1"),
    ("pt-br+f2", "Feminina 2"),
    ("pt-br+f4", "Feminina 4"),
    ("pt-br+klatt", "Klatt (sintética)"),
    ("pt-br+whisper", "Sussurro"),
)


class EspeakEngine:
    name = "espeak"
    label = "espeak-ng (leve)"

    def __init__(self, timeout_s: float) -> None:
        self._binary = shutil.which("espeak-ng") or shutil.which("espeak")
        self._timeout_s = timeout_s
        self._valid_ids = {voice_id for voice_id, _ in ESPEAK_VOICES}

    def check(self) -> tuple[bool, str]:
        if not self._binary:
            return False, "espeak-ng não encontrado (sudo dnf install espeak-ng)"
        return True, self._binary

    def voices(self) -> list[VoiceOption]:
        return [VoiceOption(self.name, voice_id, label) for voice_id, label in ESPEAK_VOICES]

    def has_voice(self, voice_id: str) -> bool:
        return voice_id in self._valid_ids

    def synthesize(self, text: str, profile: VoiceProfile) -> AudioClip:
        if not self._binary:
            raise SynthesisError("espeak-ng indisponível")
        voice = profile.voice if self.has_voice(profile.voice) else "pt-br"
        pitch = max(0, min(99, round(50 + (profile.pitch - 1.0) * 120)))
        command = [
            self._binary, "-v", voice,
            "-s", str(round(170 * profile.rate)),
            "-p", str(pitch),
            "-a", str(round(100 * profile.volume)),
            "--stdout", "--stdin",
        ]
        try:
            # Texto por stdin: nunca vira argumento, então não é interpretado como opção.
            result = subprocess.run(
                command, input=text.encode("utf-8"), capture_output=True,
                timeout=self._timeout_s, check=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise SynthesisError("espeak-ng excedeu o tempo limite") from exc
        except subprocess.CalledProcessError as exc:
            raise SynthesisError(exc.stderr.decode(errors="replace").strip()) from exc
        with wave.open(io.BytesIO(result.stdout)) as wav:
            return AudioClip(wav.readframes(wav.getnframes()), wav.getframerate())


# ---------------------------------------------------------------- Piper (neural)

PIPER_CATALOG = {
    "pt_BR-faber-medium": ("Faber · masculina, neutra", 63),
    "pt_BR-cadu-medium": ("Cadu · masculina", 62),
    "pt_BR-jeff-medium": ("Jeff · masculina", 62),
    "pt_BR-edresson-low": ("Edresson · masculina (baixa qualidade)", 63),
}
_PIPER_ID = re.compile(r"^[a-z]{2}_[A-Z]{2}-[\w]+-(x_low|low|medium|high)$")


class PiperEngine:
    """Piper rodando no próprio processo: o modelo é carregado uma vez (~1,3 s)
    e cada frase sai em ~0,1 s. Só um modelo fica em memória (~100 MB)."""

    name = "piper"
    label = "Piper (neural)"

    def __init__(self, voices_dir: Path, download_timeout_s: float) -> None:
        self._dir = voices_dir
        self._download_timeout_s = download_timeout_s
        self._lock = threading.Lock()
        self._loaded: tuple[str, object] | None = None

    def check(self) -> tuple[bool, str]:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False, "piper-tts não instalado (pip install -r requirements.txt)"
        return True, f"{len(self._installed_ids())} voz(es) instalada(s)"

    def _model_path(self, voice_id: str) -> Path:
        # Valida o id antes de virar caminho: o perfil vem de um JSON editável,
        # e um id como "../../algo" não pode escapar da pasta de vozes.
        if not _PIPER_ID.match(voice_id):
            raise SynthesisError(f"Identificador de voz inválido: {voice_id!r}")
        return self._dir / f"{voice_id}.onnx"

    def _installed_ids(self) -> list[str]:
        if not self._dir.is_dir():
            return []
        return sorted(
            p.name.removesuffix(".onnx") for p in self._dir.glob("*.onnx")
            if _PIPER_ID.match(p.stem) and p.with_name(p.name + ".json").is_file()
        )

    def has_voice(self, voice_id: str) -> bool:
        return voice_id in self._installed_ids()

    def voices(self) -> list[VoiceOption]:
        installed = set(self._installed_ids())
        options = [
            VoiceOption(self.name, voice_id, label, voice_id in installed, size)
            for voice_id, (label, size) in PIPER_CATALOG.items()
        ]
        options += [VoiceOption(self.name, v, v) for v in sorted(installed - PIPER_CATALOG.keys())]
        return options

    def preload(self, voice_id: str) -> None:
        try:
            self._voice(voice_id)
        except Exception as exc:
            log.warning("Pré-carregamento da voz %s falhou: %s", voice_id, exc)

    def _voice(self, voice_id: str):
        with self._lock:
            if self._loaded and self._loaded[0] == voice_id:
                return self._loaded[1]
            path = self._model_path(voice_id)
            if not path.is_file():
                raise SynthesisError(f"Voz {voice_id} não instalada")
            from piper import PiperVoice

            self._loaded = None  # libera o modelo anterior antes de carregar outro
            voice = PiperVoice.load(str(path))
            self._loaded = (voice_id, voice)
            log.info("Modelo de voz carregado: %s", voice_id)
            return voice

    def synthesize(self, text: str, profile: VoiceProfile) -> AudioClip:
        from piper import SynthesisConfig

        voice = self._voice(profile.voice)
        # Piper não tem controle de tom. Truque: tocar a uma taxa maior sobe o
        # tom e acelera; compensamos alongando os fonemas na mesma proporção.
        config = SynthesisConfig(
            length_scale=profile.pitch / profile.rate,
            volume=profile.volume,
        )
        pcm = b"".join(chunk.audio_int16_bytes for chunk in voice.synthesize(text, syn_config=config))
        return AudioClip(pcm, round(voice.config.sample_rate * profile.pitch))

    def install(self, voice_id: str) -> None:
        """Baixa uma voz do catálogo oficial (HuggingFace rhasspy/piper-voices).

        Baixa numa pasta temporária e só move ao final: uma queda de rede não
        deixa um modelo truncado que quebraria o carregamento depois.
        """
        if voice_id not in PIPER_CATALOG:
            raise SynthesisError(f"Voz fora do catálogo: {voice_id}")
        self._dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self._dir, prefix=".download-") as tmp:
            try:
                subprocess.run(
                    [sys.executable, "-m", "piper.download_voices", voice_id, "--download-dir", tmp],
                    capture_output=True, timeout=self._download_timeout_s, check=True,
                )
            except subprocess.TimeoutExpired as exc:
                raise SynthesisError("Download excedeu o tempo limite") from exc
            except subprocess.CalledProcessError as exc:
                detail = exc.stderr.decode(errors="replace").strip().splitlines()
                raise SynthesisError(detail[-1] if detail else "falha no download") from exc
            for suffix in (".onnx.json", ".onnx"):  # o .onnx por último: ele marca "instalada"
                Path(tmp, voice_id + suffix).replace(self._dir / (voice_id + suffix))
