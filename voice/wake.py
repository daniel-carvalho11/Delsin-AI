"""Palavra de ativação "Delsin" — 100% local (nenhum áudio sai da máquina).

Pipeline (thread "delsin-wake"):
  pw-record contínuo (16 kHz) → detector de voz por energia → trechos de
  0,3–3 s → Whisper "tiny" (faster-whisper, CPU) → procura "Delsin" no início.

Por que Whisper: testado contra Vosk, que ouve "Delsin" como "assim" (falsos
positivos o tempo todo). O Whisper com a dica de vocabulário acerta a palavra,
e filtros de confiança descartam alucinações em ruído.

Modelo: "base" por padrão (~145 MB, ~0,4–0,6 s de CPU por trecho de fala;
acertou 25/30 em testes sintéticos). "tiny" é mais leve mas erra "Delsin"
dito sozinho. Troque com DELSIN_WAKE_MODEL=tiny|base|small. Em silêncio, só
o cálculo de energia roda. Dica de uso: "Ei, Delsin" é mais confiável.
"""
from __future__ import annotations

import array
import logging
import math
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger("delsin.voice.wake")

RATE = 16000
FRAME = 480                      # 30 ms
MIN_SPEECH_S, MAX_SPEECH_S = 0.3, 3.0
END_SILENCE_S = 0.5
# Variações que o Whisper produz para "Delsin" (medidas com vozes sintéticas).
WAKE_PATTERN = re.compile(r"^\W*(?:e[iy]?\W+|ok\W+|oi\W+)?(del+\s?[sc]i[nm]?|des{1,2}i[nm]|dell?\s?sim|delsi)\b",
                          re.IGNORECASE)


def strip_wake(text: str) -> str:
    """'Delsin, que horas são?' -> 'que horas são?' (vazio se só houver a palavra)."""
    match = WAKE_PATTERN.search(text.strip())
    rest = text.strip()[match.end():] if match else text
    return rest.strip(" ,.!?;:-").strip()


def is_wake(text: str) -> bool:
    # "Delsin, Ei Delsin, Ei Delsin." = o Whisper repetindo a dica sobre ruído, não fala real.
    if len(re.findall(r"del+\s?[sc]i", text, re.IGNORECASE)) > 1:
        return False
    return bool(WAKE_PATTERN.search(text.strip()))


class WakeWordListener:
    def __init__(self, model_dir: Path, on_wake: Callable[[bytes, str], None],
                 is_muted: Callable[[], bool], device: Callable[[], str], model_size: str = "base") -> None:
        self._model_dir = model_dir
        self.model_size = model_size
        self._on_wake = on_wake
        self._is_muted = is_muted      # True enquanto o Delsin fala ou já está ouvindo
        self._device = device
        self._model = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def check(self) -> tuple[bool, str]:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False, "faster-whisper não instalado (pip install -r requirements.txt)"
        return True, f"local (Whisper {self.model_size})"

    def start(self) -> None:
        """Carrega o modelo (lento na 1ª vez: download) e começa a ouvir. Chamar fora da GUI."""
        if self.running:
            return
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model_dir.mkdir(parents=True, exist_ok=True)
            started = time.monotonic()
            try:  # já baixado: carrega sem consultar a internet
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8",
                                           download_root=str(self._model_dir), local_files_only=True)
            except Exception:
                log.info("Baixando o modelo Whisper '%s' (só na primeira vez)…", self.model_size)
                self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8",
                                           download_root=str(self._model_dir))
            log.info("Modelo de ativação carregado em %.1fs", time.monotonic() - started)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="delsin-wake", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread = None

    def _run(self) -> None:
        from voice.capture import PipeWireSource

        while not self._stop.is_set():
            try:
                # max_seconds alto: o watchdog só age se o pw-record travar de vez
                with PipeWireSource(self._device(), max_seconds=24 * 3600) as source:
                    self._listen(source)
            except OSError as exc:
                log.warning("Captura da palavra de ativação falhou (%s); tentando de novo em 3 s", exc)
                self._stop.wait(3)

    def _listen(self, source) -> None:
        noise = 300.0
        speech: list[bytes] = []
        silent_frames = 0
        while not self._stop.is_set():
            frame = source.stream.read(FRAME)
            if len(frame) < FRAME * 2:
                return  # pw-record terminou; o laço externo reabre
            samples = array.array("h", frame)
            rms = math.sqrt(sum(s * s for s in samples) / len(samples))
            if self._is_muted():
                speech, silent_frames = [], 0
                continue
            loud = rms > max(noise * 3.0, 400)
            if not speech:
                noise = 0.97 * noise + 0.03 * rms  # piso de ruído adaptativo (só fora da fala)
                if loud:
                    speech = [frame]
                continue
            speech.append(frame)
            silent_frames = 0 if loud else silent_frames + 1
            duration = len(speech) * FRAME / RATE
            if silent_frames * FRAME / RATE >= END_SILENCE_S or duration >= MAX_SPEECH_S:
                if duration >= MIN_SPEECH_S:
                    self._check_segment(b"".join(speech))
                speech, silent_frames = [], 0

    def _check_segment(self, pcm: bytes) -> None:
        import numpy as np

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
        segments, _ = self._model.transcribe(
            audio, language="pt", initial_prompt="Delsin.", beam_size=1,
            vad_filter=False, condition_on_previous_text=False, without_timestamps=True,
        )
        segments = list(segments)
        if not segments:
            return
        first = segments[0]
        text = " ".join(s.text.strip() for s in segments)
        # Filtros contra alucinação: o Whisper inventa a palavra da dica em ruído.
        confident = first.no_speech_prob < 0.6 and first.avg_logprob > -1.0
        log.debug("Ativação? %r (no_speech=%.2f, logprob=%.2f)", text, first.no_speech_prob, first.avg_logprob)
        if confident and is_wake(text) and not self._is_muted():
            log.info("Palavra de ativação detectada: %r", text)
            self._on_wake(pcm, text)  # o trecho vai junto: pode já conter o comando
