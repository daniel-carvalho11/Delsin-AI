"""Reprodução de PCM via subprocesso (pw-play > paplay > aplay).

Um processo por fala: interromper = matar o processo. Nada de stream de
áudio aberto dentro do Python que possa travar o interpretador.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import threading

from voice.engines import AudioClip

log = logging.getLogger("delsin.voice.player")


def _commands(rate: int) -> list[list[str]]:
    return [
        ["pw-play", "--raw", "--rate", str(rate), "--channels", "1", "--format", "s16", "-"],
        ["paplay", "--raw", f"--rate={rate}", "--channels=1", "--format=s16le"],
        ["aplay", "-q", "-t", "raw", "-f", "S16_LE", "-c", "1", "-r", str(rate), "-"],
    ]


class PcmPlayer:
    def __init__(self) -> None:
        self._tool = next((cmd[0] for cmd in _commands(1) if shutil.which(cmd[0])), None)
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()

    @property
    def tool(self) -> str | None:
        return self._tool

    def play(self, clip: AudioClip) -> bool:
        """Bloqueia até o fim do áudio. Retorna False se foi interrompido ou falhou."""
        if not self._tool or not clip.pcm:
            return False
        command = next(cmd for cmd in _commands(clip.sample_rate) if cmd[0] == self._tool)
        try:
            with self._lock:
                self._proc = subprocess.Popen(
                    command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
                )
                proc = self._proc
            try:
                _, stderr = proc.communicate(clip.pcm, timeout=clip.duration_s + 5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                log.warning("Reprodução travou e foi encerrada")
                return False
            if proc.returncode not in (0, -15):
                detail = stderr.decode(errors="replace").strip() or "sem mensagem"
                log.warning("%s retornou %s: %s", self._tool, proc.returncode, detail)
            return proc.returncode == 0
        except OSError as exc:
            log.error("Falha ao executar %s: %s", self._tool, exc)
            return False
        finally:
            with self._lock:
                self._proc = None

    def stop(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                self._proc.terminate()
