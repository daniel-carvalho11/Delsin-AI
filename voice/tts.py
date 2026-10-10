"""Text-to-Speech via espeak-ng em subprocesso.

Por que não pyttsx3: no Linux ele usa o espeak via driver em processo e o
runAndWait() é conhecido por travar quando chamado de threads ou mais de uma
vez por sessão. Um subprocesso dá isolamento total: se travar, é morto por
timeout e o Delsin segue de pé.

O backend é trocável: para voz natural, substitua _command() por Piper
(TTS neural local) mantendo a mesma interface.
"""
from __future__ import annotations

import logging
import queue
import shutil
import subprocess
import threading

from config.settings import VoiceSettings

log = logging.getLogger("delsin.voice.tts")


class TextToSpeech:
    def __init__(self, settings: VoiceSettings) -> None:
        self.settings = settings
        self.available = False
        self._binary = shutil.which("espeak-ng") or shutil.which("espeak")
        self._queue: queue.Queue[str | None] = queue.Queue(maxsize=settings.tts_queue_size)
        self._proc: subprocess.Popen[str] | None = None
        self._proc_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def initialize(self) -> tuple[bool, str]:
        if not self._binary:
            return False, "espeak-ng não encontrado (sudo dnf install espeak-ng)"
        self._thread = threading.Thread(target=self._run, name="delsin-tts", daemon=True)
        self._thread.start()
        self.available = True
        return True, f"Síntese: {self._binary} (voz {self.settings.tts_voice})"

    @property
    def speaking(self) -> bool:
        with self._proc_lock:
            return self._proc is not None and self._proc.poll() is None

    def say(self, text: str) -> None:
        if not self.available or not text.strip():
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            log.warning("Fila de fala cheia — mensagem descartada")

    def stop(self) -> None:
        """Interrompe a fala atual e esvazia a fila (ex.: antes de ouvir o microfone)."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        with self._proc_lock:
            if self._proc is not None and self._proc.poll() is None:
                self._proc.terminate()

    def shutdown(self) -> None:
        if not self.available:
            return
        self.stop()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=2)
        self.available = False

    def _command(self) -> list[str]:
        # Texto entra por stdin (--stdin): nunca vira argumento de linha de
        # comando, então não há como ser interpretado como opção ou shell.
        return [self._binary, "-v", self.settings.tts_voice,
                "-s", str(self.settings.tts_rate), "--stdin"]

    def _run(self) -> None:
        while (text := self._queue.get()) is not None:
            self._speak(text)

    def _speak(self, text: str) -> None:
        try:
            with self._proc_lock:
                self._proc = subprocess.Popen(
                    self._command(),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            proc = self._proc
            try:
                _, stderr = proc.communicate(text, timeout=self.settings.tts_timeout_s)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                log.warning("TTS excedeu %.0fs — processo encerrado", self.settings.tts_timeout_s)
                return
            if proc.returncode not in (0, -15) and stderr:  # -15 = interrompido por stop()
                log.warning("espeak-ng retornou %s: %s", proc.returncode, stderr.strip())
        except OSError as exc:
            log.error("Falha ao executar TTS: %s", exc)
        finally:
            with self._proc_lock:
                self._proc = None
