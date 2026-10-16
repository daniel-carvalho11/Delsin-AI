"""Captura de microfone via subprocesso pw-record (PipeWire).

Vantagens sobre abrir o dispositivo pelo PyAudio:
- escolhe QUALQUER entrada do PipeWire pelo nome (fone, USB, Bluetooth, embutido);
- interromper = matar um processo; nada trava dentro do Python;
- mede o nível de pico, permitindo detectar um microfone mudo.
"""
from __future__ import annotations

import array
import subprocess
import threading

import speech_recognition as sr

SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2
FULL_SCALE = 32768


class _PipeStream:
    """Adapta o stdout do pw-record à interface read(frames) que o SpeechRecognition usa."""

    def __init__(self, pipe) -> None:
        self._pipe = pipe
        self.peak = 0

    def read(self, frames: int) -> bytes:
        data = self._pipe.read(frames * SAMPLE_WIDTH)
        usable = len(data) - len(data) % SAMPLE_WIDTH
        if usable:
            samples = array.array("h", data[:usable])
            self.peak = max(self.peak, max(samples), -min(samples))
        return data


class PipeWireSource(sr.AudioSource):
    SAMPLE_RATE = SAMPLE_RATE
    SAMPLE_WIDTH = SAMPLE_WIDTH
    CHUNK = 1024

    def __init__(self, target: str | None, max_seconds: float) -> None:
        self.target = target or None
        self.max_seconds = max_seconds
        self.stream: _PipeStream | None = None
        self.peak = 0
        self._proc: subprocess.Popen[bytes] | None = None
        self._watchdog: threading.Timer | None = None

    def __enter__(self) -> PipeWireSource:
        command = ["pw-record", "--raw", "--rate", str(SAMPLE_RATE), "--channels", "1", "--format", "s16"]
        if self.target:
            command += ["--target", self.target]
        command.append("-")
        self._proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.stream = _PipeStream(self._proc.stdout)
        # O SpeechRecognition mede o tempo pelo áudio recebido, não pelo relógio.
        # Se o pw-record parar de entregar dados, read() bloquearia para sempre;
        # o watchdog mata o processo e read() passa a retornar vazio.
        self._watchdog = threading.Timer(self.max_seconds, self._kill)
        self._watchdog.daemon = True
        self._watchdog.start()
        return self

    def _kill(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            self._proc.kill()

    def __exit__(self, *_exc) -> None:
        if self._watchdog:
            self._watchdog.cancel()
        if self.stream:
            self.peak = self.stream.peak
        if self._proc is not None:
            if self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait()
            if self._proc.stdout:
                self._proc.stdout.close()
        self.stream = None


def measure_peak(target: str | None, seconds: float) -> float:
    """Grava por `seconds` e retorna o pico (0.0–1.0). Usado no teste de microfone."""
    with PipeWireSource(target, seconds + 3) as source:
        frames_needed = int(SAMPLE_RATE * seconds)
        while frames_needed > 0:
            if not source.stream.read(min(source.CHUNK, frames_needed)):
                break
            frames_needed -= source.CHUNK
    return source.peak / FULL_SCALE
