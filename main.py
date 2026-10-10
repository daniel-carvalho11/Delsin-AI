#!/usr/bin/env python3
"""Delsin — ponto de entrada (composition root).

Este arquivo é o único lugar que conhece todos os módulos ao mesmo tempo.
Ele os instancia, liga uns aos outros por callbacks/filas e controla o
ciclo de vida. Nenhum outro módulo importa GUI + Core + Voz juntos.

Modelo de threads:
  main thread ........ Tkinter (única que toca em widgets)
  delsin-boot ........ inicialização de skills/voz (não congela a janela)
  delsin-listen ...... captura de microfone + STT (sob demanda)
  delsin-dispatch/skill  roteamento e execução (pools do Agent)
  delsin-tts ......... fila de fala (síntese + player em subprocesso)
  delsin-telemetry ... amostras de CPU/memória/disco a cada 2 s
  delsin-voice-dl .... download de vozes (sob demanda)
Comunicação para a GUI: somente via queue.Queue.
"""
from __future__ import annotations

import logging
import queue
import signal
import sys
import threading

from config import DEFAULT_PERSONA, ensure_dirs, load_settings
from config.settings import APP_NAME, APP_VERSION, LOG_DIR, VOICE_PROFILE_PATH, VOICES_DIR, Settings
from config.voice_profile import VoiceProfile, load_profile, save_profile
from core import Agent, Request, Response, Source
from core.logger import LogItem, setup_logging
from gui import (
    Activity, ActivityEvent, Dashboard, DashboardCallbacks, MessageEvent, MetricsEvent, MetricView,
    ModuleState, StatusEvent, UiEvent, VoiceCatalogEvent,
)
from services.telemetry import TelemetrySampler
from skills import discover_skills
from voice import SpeechToText, STTError, SynthesisError, TextToSpeech

log = logging.getLogger("delsin.app")

TELEMETRY_INTERVAL_S = 2.0


class DelsinApp:
    def __init__(self, settings: Settings, log_queue: queue.Queue[LogItem]) -> None:
        self.settings = settings
        self.events: queue.Queue[UiEvent] = queue.Queue(maxsize=1000)
        self.agent = Agent(settings.core, DEFAULT_PERSONA)
        self.stt = SpeechToText(settings.voice)
        self.tts = TextToSpeech(
            settings.voice, load_profile(VOICE_PROFILE_PATH), VOICES_DIR,
            on_speaking=lambda speaking: self._set_activity_flag("speaking", speaking),
        )
        self.telemetry = TelemetrySampler()
        self.speak_responses = False
        self._shutdown = threading.Event()
        self._activity_lock = threading.Lock()
        self._activity_flags = {"listening": False, "speaking": False}
        self._pending_requests = 0
        self._activity = Activity.IDLE

        self.window = Dashboard(
            events=self.events,
            logs=log_queue,
            callbacks=DashboardCallbacks(
                on_submit=lambda text: self.submit(text, Source.TEXT),
                on_listen=self.listen,
                on_toggle_voice=self._set_voice_output,
                on_close=self.shutdown,
                get_voice_catalog=self.tts.catalog,
                on_preview_voice=self.tts.preview,
                on_save_voice=self._save_voice,
                on_install_voice=self._install_voice,
            ),
            app_name=APP_NAME,
            version=APP_VERSION,
        )

    # ---------- comunicação com a GUI ----------

    def _post(self, event: UiEvent) -> None:
        if self._shutdown.is_set():
            return
        try:
            self.events.put_nowait(event)
        except queue.Full:
            log.warning("Fila da GUI cheia — evento descartado: %s", type(event).__name__)

    def _status(self, module: str, state: ModuleState, detail: str = "") -> None:
        self._post(StatusEvent(module, state, detail))

    def _set_activity_flag(self, flag: str, value: bool) -> None:
        with self._activity_lock:
            self._activity_flags[flag] = value
            self._publish_activity()

    def _change_pending(self, delta: int) -> None:
        with self._activity_lock:
            self._pending_requests += delta
            self._publish_activity()

    def _publish_activity(self) -> None:
        """Prioridade: falando > ouvindo > processando > ocioso. Chamar com o lock."""
        if self._activity_flags["speaking"]:
            activity = Activity.SPEAKING
        elif self._activity_flags["listening"]:
            activity = Activity.LISTENING
        elif self._pending_requests > 0:
            activity = Activity.PROCESSING
        else:
            activity = Activity.IDLE
        if activity is not self._activity:
            self._activity = activity
            self._post(ActivityEvent(activity))

    # ---------- inicialização ----------

    def run(self) -> None:
        threading.Thread(target=self._boot, name="delsin-boot", daemon=True).start()
        threading.Thread(target=self._telemetry_loop, name="delsin-telemetry", daemon=True).start()
        self.window.mainloop()

    def _boot(self) -> None:
        """Inicializa módulos em sequência fora da main thread.

        Falha em um módulo NÃO derruba os outros: o Delsin degrada para
        modo texto se o áudio não estiver disponível.
        """
        self._status("core", ModuleState.ONLINE, f"router: {type(self.agent.router).__name__}")
        self._status("llm", ModuleState.OFFLINE, "não configurado")

        self._status("skills", ModuleState.STARTING, "descobrindo…")
        loaded = sum(self.agent.register(s) for s in discover_skills())
        self._status("skills", ModuleState.ONLINE if loaded else ModuleState.ERROR, f"{loaded} carregadas")

        for module, component in (("tts", self.tts), ("stt", self.stt)):
            self._status(module, ModuleState.STARTING, "verificando…")
            try:
                ok, detail = component.initialize()
            except Exception as exc:  # binding nativo pode falhar de formas inesperadas
                log.exception("Falha inesperada ao iniciar %s", module)
                ok, detail = False, str(exc)
            (log.info if ok else log.warning)("%s: %s", module.upper(), detail)
            self._status(module, ModuleState.ONLINE if ok else ModuleState.ERROR, detail)

        self._post(MessageEvent("delsin", DEFAULT_PERSONA.greeting))

    def _telemetry_loop(self) -> None:
        while not self._shutdown.wait(TELEMETRY_INTERVAL_S):
            metrics = tuple(MetricView(m.key, m.label, m.fraction, m.display) for m in self.telemetry.sample())
            self._post(MetricsEvent(metrics))

    # ---------- fluxo de comandos ----------

    def submit(self, text: str, source: Source) -> None:
        request = Request(text=text, source=source)
        self._post(MessageEvent("user", text, "voz" if source is Source.VOICE else "texto"))
        self._change_pending(+1)
        self.agent.submit(request, self._on_response)

    def _on_response(self, request: Request, response: Response) -> None:
        # Roda numa thread do Agent: apenas enfileira, nunca toca na GUI.
        self._change_pending(-1)
        status = "ok" if response.success else "falha"
        meta = f"{status}  ·  {response.skill}  ·  {response.latency_ms:.0f} ms"
        self._post(MessageEvent("delsin", response.text, meta, failed=not response.success,
                                latency_ms=response.latency_ms))
        wants_voice = self.speak_responses or request.source is Source.VOICE
        if response.speak and wants_voice:
            self.tts.say(response.text)

    def listen(self) -> None:
        if self.stt.busy:
            return
        threading.Thread(target=self._listen_worker, name="delsin-listen", daemon=True).start()

    def _listen_worker(self) -> None:
        # Interrompe a fala antes de abrir o microfone: sem isso o Delsin
        # transcreve a própria voz saindo da caixa de som (eco).
        self.tts.stop()
        self._status("stt", ModuleState.ACTIVE, "ouvindo…")
        self._set_activity_flag("listening", True)
        try:
            text = self.stt.listen_once()
        except STTError as exc:
            log.warning("STT: %s", exc)
            self._post(MessageEvent("system", str(exc), "voz", failed=True))
            text = None
        finally:
            self._set_activity_flag("listening", False)
            self._status("stt", ModuleState.ONLINE, "pronto")
        if text:
            self.submit(text, Source.VOICE)

    def _set_voice_output(self, enabled: bool) -> None:
        self.speak_responses = enabled
        log.info("Resposta por voz %s", "ativada" if enabled else "desativada")
        if not enabled:
            self.tts.stop()

    # ---------- voz ----------

    def _save_voice(self, profile: VoiceProfile) -> None:
        effective = self.tts.set_profile(profile)
        try:
            save_profile(effective, VOICE_PROFILE_PATH)
        except OSError as exc:
            log.error("Não foi possível salvar o perfil de voz: %s", exc)
        log.info("Perfil de voz aplicado: %s", self.tts.describe())
        self._status("tts", ModuleState.ONLINE, self.tts.describe())

    def _install_voice(self, engine: str, voice_id: str) -> None:
        def worker() -> None:
            self._status("tts", ModuleState.STARTING, f"baixando {voice_id}…")
            log.info("Baixando voz %s…", voice_id)
            try:
                self.tts.install_voice(engine, voice_id)
                message = f"Voz {voice_id} instalada. Selecione-a e clique em TESTAR."
                log.info(message)
            except SynthesisError as exc:
                message = f"Falha no download: {exc}"
                log.error(message)
            self._status("tts", ModuleState.ONLINE, self.tts.describe())
            self._post(VoiceCatalogEvent(self.tts.catalog(), message))

        threading.Thread(target=worker, name="delsin-voice-dl", daemon=True).start()

    # ---------- desligamento ----------

    def shutdown(self) -> None:
        if self._shutdown.is_set():
            return
        log.info("Desligando…")
        self._shutdown.set()
        self.tts.shutdown()
        self.agent.shutdown()


def main() -> int:
    settings = load_settings()
    ensure_dirs()
    log_queue = setup_logging(LOG_DIR, debug=settings.debug)
    log.info("%s v%s iniciando (Python %s)", APP_NAME, APP_VERSION, sys.version.split()[0])

    try:
        app = DelsinApp(settings, log_queue)
    except Exception as exc:  # ex.: sem $DISPLAY / sessão gráfica
        log.critical("Não foi possível abrir a interface: %s", exc, exc_info=settings.debug)
        return 1

    # Ctrl+C no terminal: o mainloop do Tk só devolve controle ao Python entre
    # eventos; o after() periódico da GUI garante que o sinal seja processado.
    signal.signal(signal.SIGINT, lambda *_: app.window.after(0, app.window.close))
    signal.signal(signal.SIGTERM, lambda *_: app.window.after(0, app.window.close))

    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
