"""Perfil de voz escolhido pelo usuário, persistido em JSON.

Fica em config/ porque é compartilhado por voice/ (que o aplica) e gui/
(que o edita) — e nenhum dos dois pode importar o outro.
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

log = logging.getLogger("delsin.config")

ENGINES = ("elevenlabs", "piper", "espeak")
# Modelos ElevenLabs oferecidos na GUI: (id, rótulo). flash = rápido e barato;
# multilingual_v2 = sotaque pt-BR mais natural nas vozes verificadas, o dobro de créditos.
ELEVEN_MODELS = (
    ("eleven_multilingual_v2", "Natural pt-BR (multilingual v2)"),
    ("eleven_flash_v2_5", "Rápido e econômico (flash v2.5)"),
)
RATE_RANGE = (0.6, 1.6)     # multiplicador de velocidade
PITCH_RANGE = (0.75, 1.30)  # multiplicador de tom
VOLUME_RANGE = (0.2, 1.5)   # multiplicador de volume
# Nomes de nós do PipeWire (ex.: alsa_input.pci-0000_00_1f.3-platform-skl_hda_dsp_generic.HiFi__Mic1__source)
_DEVICE_NAME = re.compile(r"^[\w.\-:@]{0,200}$")


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    low, high = bounds
    return min(max(float(value), low), high)


@dataclass(frozen=True, slots=True)
class VoiceProfile:
    engine: str = "piper"
    voice: str = "pt_BR-faber-medium"
    rate: float = 1.0
    pitch: float = 1.0
    volume: float = 1.0
    input_device: str = ""  # microfone (nome do nó PipeWire); "" = padrão do sistema
    cloud_model: str = "eleven_multilingual_v2"  # modelo da ElevenLabs
    wake_word: bool = False  # ouvir "Delsin" continuamente (local)

    def clamped(self) -> VoiceProfile:
        """Normaliza valores vindos de arquivo ou da GUI para faixas seguras."""
        return replace(
            self,
            engine=self.engine if self.engine in ENGINES else "espeak",
            voice=str(self.voice),
            rate=round(_clamp(self.rate, RATE_RANGE), 2),
            pitch=round(_clamp(self.pitch, PITCH_RANGE), 2),
            volume=round(_clamp(self.volume, VOLUME_RANGE), 2),
            input_device=self.input_device if _DEVICE_NAME.match(str(self.input_device)) else "",
            cloud_model=self.cloud_model if self.cloud_model in dict(ELEVEN_MODELS) else ELEVEN_MODELS[0][0],
            wake_word=bool(self.wake_word),
        )


@dataclass(frozen=True, slots=True)
class VoiceOption:
    engine: str
    id: str
    label: str
    installed: bool = True
    size_mb: int = 0


@dataclass(frozen=True, slots=True)
class InputOption:
    id: str
    label: str
    is_default: bool = False


@dataclass(frozen=True, slots=True)
class EngineInfo:
    name: str
    label: str
    available: bool
    detail: str = ""


@dataclass(frozen=True, slots=True)
class VoiceCatalog:
    engines: tuple[EngineInfo, ...]
    voices: dict[str, tuple[VoiceOption, ...]] = field(default_factory=dict)
    profile: VoiceProfile = field(default_factory=VoiceProfile)
    inputs: tuple[InputOption, ...] = ()
    elevenlabs_key: str = "não configurada"  # já mascarada; a chave real nunca vai para a GUI


def load_profile(path: Path) -> VoiceProfile:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return VoiceProfile()
    except (OSError, ValueError) as exc:
        log.warning("Perfil de voz ilegível (%s) — usando padrão", exc)
        return VoiceProfile()
    if not isinstance(raw, dict):
        return VoiceProfile()
    known = {key: raw[key] for key in VoiceProfile.__dataclass_fields__ if key in raw}
    try:
        return VoiceProfile(**known).clamped()
    except (TypeError, ValueError):
        log.warning("Perfil de voz inválido — usando padrão")
        return VoiceProfile()


def save_profile(profile: VoiceProfile, path: Path) -> None:
    """Escrita atômica: arquivo temporário + rename, nunca deixa JSON pela metade."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(profile.clamped()), indent=2, ensure_ascii=False)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".voice-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
