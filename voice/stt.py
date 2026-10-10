"""Speech-to-Text: captura do microfone + reconhecimento.

Decisões para não travar no Linux:
- Só uma captura por vez (lock não-bloqueante): duas aberturas simultâneas
  do mesmo dispositivo podem bloquear dentro da PortAudio.
- O stream é aberto via context manager e FECHADO antes da chamada de rede:
  o microfone é liberado mesmo se o reconhecimento demorar ou falhar.
- Dispositivo preferido "pipewire"/"default": abrir hw:X,Y direto compete
  com o PipeWire pelo hardware (erro "Device unavailable" ou bloqueio).
- Todos os passos têm timeout (escuta, frase, rede).
"""
from __future__ import annotations

import logging
import threading

from config.settings import VoiceSettings
from voice.alsa import silence_alsa_errors

log = logging.getLogger("delsin.voice.stt")


class STTError(Exception):
    """Falha recuperável de STT, com mensagem apresentável ao usuário."""


class SpeechToText:
    def __init__(self, settings: VoiceSettings) -> None:
        self.settings = settings
        self.available = False
        self._sr = None
        self._recognizer = None
        self._device_index: int | None = None
        self._capture_lock = threading.Lock()

    def initialize(self) -> tuple[bool, str]:
        """Verifica dependências e dispositivos. Seguro para rodar fora da GUI."""
        try:
            import speech_recognition as sr
            import pyaudio  # noqa: F401  (confirma que o binding nativo carrega)
        except ImportError as exc:
            return False, f"Dependência ausente: {exc.name}. Veja requirements.txt"

        silence_alsa_errors()
        try:
            names = sr.Microphone.list_microphone_names()
        except OSError as exc:
            return False, f"PortAudio não acessou os dispositivos: {exc}"
        if not names:
            return False, "Nenhum dispositivo de áudio encontrado"

        self._device_index = self._pick_device(names)
        device_label = names[self._device_index] if self._device_index is not None else "padrão do sistema"

        recognizer = sr.Recognizer()
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.8
        recognizer.operation_timeout = self.settings.recognition_timeout_s

        self._sr, self._recognizer = sr, recognizer
        self.available = True
        return True, f"Microfone: {device_label}"

    def _pick_device(self, names: list[str]) -> int | None:
        lowered = [n.lower() for n in names]
        for preferred in self.settings.preferred_input_devices:
            for index, name in enumerate(lowered):
                if name == preferred:
                    return index
        return None  # PyAudio usa o dispositivo padrão

    @property
    def busy(self) -> bool:
        return self._capture_lock.locked()

    def listen_once(self) -> str | None:
        """Bloqueia até capturar e transcrever uma frase.

        Retorna o texto, None se nada foi entendido, ou levanta STTError.
        Deve ser chamado de uma thread de trabalho, nunca da GUI.
        """
        if not self.available:
            raise STTError("Módulo de voz não inicializado")
        if not self._capture_lock.acquire(blocking=False):
            raise STTError("Já existe uma captura em andamento")

        sr, rec, cfg = self._sr, self._recognizer, self.settings
        try:
            try:
                with sr.Microphone(device_index=self._device_index) as source:
                    rec.adjust_for_ambient_noise(source, duration=cfg.ambient_calibration_s)
                    log.info("Ouvindo...")
                    audio = rec.listen(
                        source,
                        timeout=cfg.listen_timeout_s,
                        phrase_time_limit=cfg.phrase_time_limit_s,
                    )
            except sr.WaitTimeoutError:
                log.info("Nenhuma fala detectada em %.0fs", cfg.listen_timeout_s)
                return None
            except OSError as exc:
                raise STTError(f"Erro no dispositivo de áudio: {exc}") from exc

            log.info("Transcrevendo (serviço remoto)...")
            try:
                return rec.recognize_google(audio, language=cfg.language)
            except sr.UnknownValueError:
                log.info("Fala não compreendida")
                return None
            except sr.RequestError as exc:
                raise STTError(f"Serviço de reconhecimento indisponível: {exc}") from exc
        finally:
            self._capture_lock.release()
