"""Text-to-Speech: fachada que une perfil de voz, motores e player.

Pipeline por fala (thread "delsin-tts"):  texto -> motor (PCM) -> player
- Uma fala por vez, em fila.
- stop() invalida tudo que estiver na fila ou sendo sintetizado (contador de
  "época") e mata a reprodução atual.
- Se o motor/voz do perfil não estiver disponível, cai para espeak-ng.

Por que não pyttsx3: no Linux o runAndWait() trava quando chamado de threads.
"""
from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from config.settings import VoiceSettings
from config.voice_profile import EngineInfo, VoiceCatalog, VoiceProfile
from voice.engines import ElevenLabsEngine, EspeakEngine, PiperEngine, SynthesisError
from voice.player import PcmPlayer

log = logging.getLogger("delsin.voice.tts")

_FALLBACK = VoiceProfile(engine="espeak", voice="pt-br")


class TextToSpeech:
    def __init__(
        self,
        settings: VoiceSettings,
        profile: VoiceProfile,
        voices_dir: Path,
        on_speaking: Callable[[bool], None] | None = None,
        elevenlabs_key: Callable[[], str | None] = lambda: None,
    ) -> None:
        self.available = False
        self.speaking = False
        self._piper = PiperEngine(voices_dir, settings.voice_download_timeout_s)
        self._espeak = EspeakEngine(settings.tts_synthesis_timeout_s)
        self._eleven = ElevenLabsEngine(elevenlabs_key, settings.elevenlabs_model, settings.elevenlabs_timeout_s)
        self._engines = {e.name: e for e in (self._eleven, self._piper, self._espeak)}
        self._engine_ok: dict[str, tuple[bool, str]] = {}
        self._player = PcmPlayer()
        self._on_speaking = on_speaking or (lambda _speaking: None)
        self._requested = profile.clamped()
        self._profile = self._requested
        self._state_lock = threading.Lock()
        self._epoch = 0
        self._queue: queue.Queue[tuple[str, VoiceProfile | None, int] | None] = queue.Queue(
            maxsize=settings.tts_queue_size
        )
        self._thread: threading.Thread | None = None

    # ---------- ciclo de vida ----------

    def initialize(self) -> tuple[bool, str]:
        if not self._player.tool:
            return False, "Nenhum player de áudio (pw-play/paplay/aplay)"
        self._engine_ok = {name: engine.check() for name, engine in self._engines.items()}
        for name, (ok, detail) in self._engine_ok.items():
            (log.info if ok else log.warning)("Motor %s: %s", name, detail)
        if not any(ok for ok, _ in self._engine_ok.values()):
            return False, "Nenhum motor de voz disponível"
        self._profile = self._resolve(self._requested)
        self._thread = threading.Thread(target=self._run, name="delsin-tts", daemon=True)
        self._thread.start()
        self.available = True
        return True, self.describe()

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

    # ---------- perfil e catálogo ----------

    @property
    def profile(self) -> VoiceProfile:
        with self._state_lock:
            return self._profile

    def set_profile(self, profile: VoiceProfile) -> VoiceProfile:
        """Aplica um perfil. Retorna o perfil efetivo (pode ter caído no fallback)."""
        requested = profile.clamped()
        resolved = self._resolve(requested)
        with self._state_lock:
            self._requested, self._profile = requested, resolved
        if resolved.engine == "piper":
            threading.Thread(target=self._piper.preload, args=(resolved.voice,),
                             name="delsin-voice-load", daemon=True).start()
        return resolved

    def describe(self) -> str:
        p = self.profile
        return f"{self._engines[p.engine].label} · {p.voice} · tom {p.pitch:.2f} · vel. {p.rate:.2f}"

    def catalog(self) -> VoiceCatalog:
        engines = tuple(
            EngineInfo(name, engine.label, *self._engine_ok.get(name, (False, "não verificado")))
            for name, engine in self._engines.items()
        )
        voices = {
            info.name: tuple(self._engines[info.name].voices()) for info in engines if info.available
        }
        return VoiceCatalog(engines, voices, self.profile)

    def refresh_engine(self, name: str) -> tuple[bool, str]:
        """Revalida um motor (ex.: após salvar a chave da ElevenLabs)."""
        self._engine_ok[name] = self._engines[name].check()
        with self._state_lock:
            self._profile = self._resolve(self._requested)
        return self._engine_ok[name]

    def install_voice(self, engine: str, voice_id: str) -> None:
        """Bloqueante (download). Chamar fora da thread da GUI."""
        if engine != "piper":
            raise SynthesisError("Somente vozes Piper são baixáveis")
        self._piper.install(voice_id)
        self._engine_ok["piper"] = self._piper.check()

    def _resolve(self, profile: VoiceProfile) -> VoiceProfile:
        engine = self._engines.get(profile.engine)
        if engine and self._engine_ok.get(profile.engine, (False,))[0] and engine.has_voice(profile.voice):
            return profile
        return self._fallback(profile)

    def _fallback(self, profile: VoiceProfile) -> VoiceProfile:
        """Piper (se houver voz instalada) e depois espeak-ng, mantendo tom/velocidade/volume."""
        if profile.engine != "piper" and self._engine_ok.get("piper", (False,))[0]:
            installed = [o.id for o in self._piper.voices() if o.installed]
            if installed:
                log.warning("Voz %s/%s indisponível — usando Piper", profile.engine, profile.voice)
                return replace(profile, engine="piper", voice=installed[0])
        if self._engine_ok.get("espeak", (False,))[0]:
            log.warning("Voz %s/%s indisponível — usando espeak-ng", profile.engine, profile.voice)
            return replace(profile, engine=_FALLBACK.engine, voice=_FALLBACK.voice)
        return profile

    # ---------- fala ----------

    def say(self, text: str, profile: VoiceProfile | None = None) -> None:
        if not self.available or not text.strip():
            return
        with self._state_lock:
            epoch = self._epoch
        try:
            self._queue.put_nowait((text, profile, epoch))
        except queue.Full:
            log.warning("Fila de fala cheia — mensagem descartada")

    def preview(self, profile: VoiceProfile, text: str) -> None:
        """Toca uma amostra com o perfil informado, sem salvá-lo."""
        self.stop()
        self.say(text, profile.clamped())

    def stop(self) -> None:
        with self._state_lock:
            self._epoch += 1
        self._player.stop()

    def _current_epoch(self) -> int:
        with self._state_lock:
            return self._epoch

    def _run(self) -> None:
        profile = self.profile
        if profile.engine == "piper":
            self._piper.preload(profile.voice)  # evita 1,3 s de espera na primeira fala
        while (item := self._queue.get()) is not None:
            text, override, epoch = item
            if epoch != self._current_epoch():
                continue  # descartada por stop()
            profile = self._resolve(override) if override else self.profile
            try:
                clip = self._engines[profile.engine].synthesize(text, profile)
            except SynthesisError as exc:
                # Ex.: créditos da ElevenLabs esgotados ou sem internet: fala com a reserva local.
                backup = self._fallback(profile)
                log.error("Síntese %s falhou (%s); tentando %s", profile.engine, exc, backup.engine)
                if backup.engine == profile.engine:
                    continue
                try:
                    clip = self._engines[backup.engine].synthesize(text, backup)
                except SynthesisError as backup_exc:
                    log.error("Reserva também falhou: %s", backup_exc)
                    continue
            except Exception:
                log.exception("Erro inesperado na síntese")
                continue
            if epoch != self._current_epoch():
                continue  # stop() chegou durante a síntese
            self.speaking = True
            self._on_speaking(True)
            log.info("Falando (%s, %.1f s de áudio)", profile.voice, clip.duration_s)
            try:
                self._player.play(clip)
            finally:
                self.speaking = False
                self._on_speaking(False)
