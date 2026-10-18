"""Speech-to-Text: captura do microfone + reconhecimento.

Dois backends de captura:
- "pipewire" (preferido): subprocesso pw-record com --target = microfone
  escolhido. Permite selecionar fone, USB, Bluetooth ou o microfone embutido,
  e mede o nível para detectar entrada muda.
- "pyaudio" (reserva, sistemas sem PipeWire): dispositivo "pipewire"/"default"
  do ALSA. Abrir hw:X,Y direto disputa o hardware com o servidor de áudio.

Decisões para não travar no Linux:
- Só uma captura por vez (lock não-bloqueante).
- O microfone é liberado ANTES da chamada de rede do reconhecimento.
- Todos os passos têm timeout (escuta, frase, rede, watchdog da captura).
"""
from __future__ import annotations

import logging
import threading

from config.settings import VoiceSettings
from config.voice_profile import InputOption
from voice.alsa import silence_alsa_errors
from voice.devices import list_inputs, pipewire_capture_available

log = logging.getLogger("delsin.voice.stt")

# Pico abaixo disso (~0,6% da escala) = entrada sem sinal (porta sem microfone,
# microfone mutado ou desconectado).
SILENT_PEAK = 200 / 32768


class STTError(Exception):
    """Falha recuperável de STT, com mensagem apresentável ao usuário."""


class SpeechToText:
    def __init__(self, settings: VoiceSettings, input_device: str = "") -> None:
        self.settings = settings
        self.available = False
        self.backend = ""
        self._sr = None
        self._recognizer = None
        self._pyaudio_index: int | None = None
        self._input_device = input_device
        self._inputs: list[InputOption] = []
        self._capture_lock = threading.Lock()

    # ---------- inicialização e dispositivos ----------

    def initialize(self) -> tuple[bool, str]:
        """Verifica dependências e dispositivos. Seguro para rodar fora da GUI."""
        try:
            import speech_recognition as sr
        except ImportError as exc:
            return False, f"Dependência ausente: {exc.name}. Veja requirements.txt"

        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8
        recognizer.operation_timeout = self.settings.recognition_timeout_s
        self._sr, self._recognizer = sr, recognizer

        if pipewire_capture_available():
            self.backend = "pipewire"
            self._inputs = list_inputs()
            if not self._inputs:
                return False, "Nenhum microfone encontrado no PipeWire"
            if self._input_device and not self._known(self._input_device):
                log.warning("Microfone salvo não encontrado (%s) — usando o padrão", self._input_device)
                self._input_device = ""
        else:
            ok, detail = self._init_pyaudio(sr)
            if not ok:
                return False, detail
        self.available = True
        return True, self.describe()

    def _init_pyaudio(self, sr) -> tuple[bool, str]:
        try:
            import pyaudio  # noqa: F401  (confirma que o binding nativo carrega)
        except ImportError as exc:
            return False, f"Dependência ausente: {exc.name}"
        silence_alsa_errors()
        try:
            names = sr.Microphone.list_microphone_names()
        except OSError as exc:
            return False, f"PortAudio não acessou os dispositivos: {exc}"
        lowered = [n.lower() for n in names]
        self._pyaudio_index = next(
            (lowered.index(p) for p in self.settings.preferred_input_devices if p in lowered), None
        )
        self.backend = "pyaudio"
        return True, ""

    def _known(self, name: str) -> bool:
        return any(option.id == name for option in self._inputs)

    def refresh_inputs(self) -> list[InputOption]:
        if self.backend == "pipewire":
            self._inputs = list_inputs()
        return list(self._inputs)

    def set_input_device(self, name: str) -> None:
        if name and self.backend == "pipewire" and not self._known(name):
            raise STTError("Microfone não encontrado; reconecte-o e tente de novo")
        self._input_device = name

    def describe(self) -> str:
        if self.backend == "pyaudio":
            return "Microfone: padrão do ALSA (PyAudio)"
        if self._input_device:
            label = next((o.label for o in self._inputs if o.id == self._input_device), self._input_device)
            return f"Microfone: {label}"
        default = next((o.label for o in self._inputs if o.is_default), "padrão do sistema")
        return f"Microfone: padrão do sistema ({default})"

    @property
    def busy(self) -> bool:
        return self._capture_lock.locked()

    # ---------- captura ----------

    def measure_level(self, device: str | None = None, seconds: float = 3.0) -> float:
        """Grava alguns segundos e retorna o pico (0.0–1.0). Para o teste de microfone."""
        if self.backend != "pipewire":
            raise STTError("Teste de nível disponível apenas com PipeWire")
        if not self._capture_lock.acquire(blocking=False):
            raise STTError("Já existe uma captura em andamento")
        try:
            from voice.capture import measure_peak

            return measure_peak(self._input_device if device is None else device, seconds)
        finally:
            self._capture_lock.release()

    def listen_once(self) -> str | None:
        """Bloqueia até capturar e transcrever uma frase.

        Retorna o texto, None se nada foi entendido, ou levanta STTError.
        Deve ser chamado de uma thread de trabalho, nunca da GUI.
        """
        if not self.available:
            raise STTError("Módulo de voz não inicializado")
        if not self._capture_lock.acquire(blocking=False):
            raise STTError("Já existe uma captura em andamento")
        try:
            audio, peak = self._capture()
            if audio is None:
                self._check_signal(peak)
                log.info("Nenhuma fala detectada em %.0fs", self.settings.listen_timeout_s)
                return None
        finally:
            self._capture_lock.release()
        return self._recognize(audio, peak)

    def _capture(self):
        sr, rec, cfg = self._sr, self._recognizer, self.settings
        if self.backend == "pipewire":
            from voice.capture import PipeWireSource

            limit = cfg.ambient_calibration_s + cfg.listen_timeout_s + cfg.phrase_time_limit_s + 3
            source = PipeWireSource(self._input_device, limit)
        else:
            source = sr.Microphone(device_index=self._pyaudio_index)
        try:
            with source:
                rec.adjust_for_ambient_noise(source, duration=cfg.ambient_calibration_s)
                log.info("Ouvindo...")
                audio = rec.listen(source, timeout=cfg.listen_timeout_s, phrase_time_limit=cfg.phrase_time_limit_s)
        except sr.WaitTimeoutError:
            audio = None
        except OSError as exc:
            raise STTError(f"Erro no dispositivo de áudio: {exc}") from exc
        peak = getattr(source, "peak", 1.0 * 32768) / 32768
        log.debug("Pico de captura: %.1f%%", peak * 100)
        return audio, peak

    def transcribe_pcm(self, pcm: bytes, rate: int = 16000) -> str | None:
        """Transcreve um trecho já gravado (ex.: o da palavra de ativação)."""
        if not self.available:
            raise STTError("Módulo de voz não inicializado")
        return self._recognize(self._sr.AudioData(pcm, rate, 2), peak=1.0)

    def _check_signal(self, peak: float) -> None:
        if peak < SILENT_PEAK:
            raise STTError(
                f"O microfone não está captando som (nível {peak:.1%}). "
                "Escolha outra entrada em ♪ → Microfone e use TESTAR MICROFONE."
            )

    def _recognize(self, audio, peak: float) -> str | None:
        sr = self._sr
        log.info("Transcrevendo (serviço remoto)...")
        try:
            return self._recognizer.recognize_google(audio, language=self.settings.language)
        except sr.UnknownValueError:
            self._check_signal(peak)
            log.info("Fala não compreendida (pico %.0f%%)", peak * 100)
            return None
        except sr.RequestError as exc:
            raise STTError(f"Serviço de reconhecimento indisponível: {exc}") from exc
