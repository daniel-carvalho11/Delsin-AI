"""Painel de controle do Delsin (customtkinter, estilo HUD).

A janela é "burra": não conhece Agent, STT nem TTS. Recebe callbacks para
as ações do usuário e consome duas filas (eventos de UI e logs) no próprio
loop de eventos.

Layout (3 colunas):
  Core Systems  | Console Neural (conversa/log) | Protocolo Temporal
  Módulos       | Barra de comando              | Neural Trace
"""
from __future__ import annotations

import platform
import queue
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import customtkinter as ctk

from config.voice_profile import VoiceCatalog, VoiceProfile
from core.logger import LogItem
from gui import theme
from gui.events import (
    Activity, ActivityEvent, MessageEvent, MetricsEvent, ModuleState, StatusEvent, UiEvent,
    VoiceCatalogEvent,
)
from gui.voice_dialog import VoiceDialog, VoiceDialogCallbacks
from gui.widgets import (
    Avatar, CalendarCanvas, GridSurface, HudPanel, ListRow, LoadSegments, MetricRow, ModuleRow,
    NeuralTrace,
)

POLL_MS = 50
MAX_ITEMS_PER_TICK = 200
MAX_LOG_LINES = 1500
MAX_CHAT_MESSAGES = 300


@dataclass(frozen=True)
class DashboardCallbacks:
    on_submit: Callable[[str], None]
    on_listen: Callable[[], None]
    on_toggle_voice: Callable[[bool], None]
    on_close: Callable[[], None]
    get_voice_catalog: Callable[[], VoiceCatalog]
    on_preview_voice: Callable[[VoiceProfile, str], None]
    on_save_voice: Callable[[VoiceProfile], None]
    on_install_voice: Callable[[str, str], None]


class Dashboard(ctk.CTk):
    MODULES = (
        ("core", "NÚCLEO"),
        ("skills", "SKILLS"),
        ("stt", "MICROFONE · STT"),
        ("tts", "VOZ · TTS"),
        ("llm", "IA · LLM"),
    )
    METRICS = (
        ("cpu", "▣", "Processamento"),
        ("memory", "▤", "Memória"),
        ("disk", "◫", "Disco"),
        ("temp", "≋", "Temperatura"),
        ("load", "∿", "Carga média"),
    )
    ACTIVITY_TEXT = {
        Activity.IDLE: "OCIOSO",
        Activity.LISTENING: "OUVINDO",
        Activity.PROCESSING: "PROCESSANDO",
        Activity.SPEAKING: "FALANDO",
    }

    def __init__(
        self,
        *,
        events: queue.Queue[UiEvent],
        logs: queue.Queue[LogItem],
        callbacks: DashboardCallbacks,
        app_name: str,
        version: str,
    ) -> None:
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=theme.BG)
        self._events, self._logs, self._cb = events, logs, callbacks
        self._app_name, self._version = app_name, version
        self._closing = False
        self._stt_ready = False
        self._module_states: dict[str, ModuleState] = {}
        self._latencies: list[float] = []
        self._started = time.monotonic()
        self._message_marks: deque[str] = deque()
        self._message_seq = 0
        self._voice_dialog: VoiceDialog | None = None

        self.title(f"{app_name} · painel de controle")
        self.geometry("1600x960")
        self.minsize(1280, 800)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(80, self._maximize)

        self._mono = theme.pick_mono()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_body()
        self._build_footer()
        self._bind_keys()

        self.after(POLL_MS, self._drain_queues)
        self._tick_clock()

    def _font(self, size: int, weight: str = "normal", slant: str = "roman") -> ctk.CTkFont:
        return ctk.CTkFont(self._mono, size, weight, slant)

    def _maximize(self) -> None:
        try:
            self.attributes("-zoomed", True)
        except Exception:
            pass  # gerenciador de janelas sem suporte: mantém o tamanho padrão

    # ================================================================ layout

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=theme.HEADER_BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(2, weight=1)

        Avatar(header).grid(row=0, column=0, rowspan=2, padx=(28, 16), pady=14)
        ctk.CTkLabel(header, text=theme.track(self._app_name), anchor="w", text_color=theme.TEXT,
                     font=self._font(22, "bold")).grid(row=0, column=1, sticky="sw", pady=(16, 0))
        self._identity = ctk.CTkLabel(
            header, text="●  IDENTIDADE VERIFICADA / PROTOCOLO: DELSIN-CORE", anchor="w",
            text_color=theme.MUTED, font=self._font(10, slant="italic"),
        )
        self._identity.grid(row=1, column=1, sticky="nw", pady=(0, 16))

        load_box = ctk.CTkFrame(header, fg_color="transparent")
        load_box.grid(row=0, column=3, rowspan=2, padx=(0, 22))
        ctk.CTkLabel(load_box, text=theme.track("Carga global"), text_color=theme.MUTED,
                     font=self._font(9)).grid(row=0, column=0, sticky="e")
        self._load_segments = LoadSegments(load_box)
        self._load_segments.grid(row=1, column=0, sticky="e", pady=(4, 0))

        for column, (glyph, command) in enumerate(
            (("♪", self.open_voice_settings), (">_", self._toggle_log)), start=4
        ):
            ctk.CTkButton(
                header, text=glyph, width=42, height=42, corner_radius=3, command=command,
                fg_color="transparent", hover_color=theme.PANEL_ALT, border_width=1,
                border_color=theme.BORDER, text_color=theme.TEXT, font=self._font(15, "bold"),
            ).grid(row=0, column=column, rowspan=2, padx=(0, 12 if column == 4 else 28))

        ctk.CTkFrame(header, height=1, fg_color=theme.BORDER, corner_radius=0).grid(
            row=2, column=0, columnspan=6, sticky="ew")

    def _build_body(self) -> None:
        body = ctk.CTkFrame(self, fg_color=theme.BG, corner_radius=0)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        columns = []
        for index, weight in enumerate((10, 11, 10)):
            body.grid_columnconfigure(index, weight=weight, uniform="cols")
            surface = GridSurface(body, width=300, height=300)
            surface.grid(row=0, column=index, sticky="nsew")
            surface.grid_columnconfigure(0, weight=1)
            columns.append(surface)
        left, center, right = columns
        outer, gap = 26, 12

        # ---- coluna esquerda
        core = HudPanel(left, self._mono, "Core Systems", fit=True)
        core.grid(row=0, column=0, sticky="new", padx=(outer, gap), pady=(outer, gap))
        self._metric_rows: dict[str, MetricRow] = {}
        for row, (key, icon, label) in enumerate(self.METRICS):
            metric = MetricRow(core.content, self._mono, icon, label)
            metric.grid(row=row, column=0, sticky="ew", pady=5)
            self._metric_rows[key] = metric
        core.refit()

        modules = HudPanel(left, self._mono, "Módulos")
        modules.grid(row=1, column=0, sticky="nsew", padx=(outer, gap), pady=(gap, outer))
        left.grid_rowconfigure(1, weight=1)
        self._status_rows: dict[str, ModuleRow] = {}
        for row, (key, label) in enumerate(self.MODULES):
            module = ModuleRow(modules.content, self._mono, label, "OFFLINE")
            module.grid(row=row, column=0, sticky="ew", pady=(0, 8))
            self._status_rows[key] = module
        modules.content.grid_rowconfigure(len(self.MODULES), weight=1)
        controls = ctk.CTkFrame(modules.content, fg_color="transparent")
        controls.grid(row=len(self.MODULES) + 1, column=0, sticky="ew")
        controls.grid_columnconfigure(0, weight=1)
        self._voice_switch = ctk.CTkSwitch(
            controls, text="RESPONDER POR VOZ", command=self._on_voice_switch, state="disabled",
            progress_color=theme.TEXT_DIM, button_color=theme.TEXT, fg_color=theme.BAR_BG,
            text_color=theme.TEXT_DIM, font=self._font(11),
        )
        self._voice_switch.grid(row=0, column=0, sticky="w", pady=(4, 10))
        self._hud_button(controls, "CONFIGURAR VOZ", self.open_voice_settings).grid(
            row=1, column=0, sticky="ew")

        # ---- coluna central
        console = HudPanel(center, self._mono, "Console Neural")
        console.grid(row=0, column=0, sticky="nsew", padx=gap, pady=(outer, gap))
        center.grid_rowconfigure(0, weight=1)
        console.content.grid_rowconfigure(0, weight=1)
        self._tab_labels = {}
        for column, (key, text) in enumerate((("chat", "CONVERSA"), ("log", "LOG")), start=1):
            label = ctk.CTkLabel(console.header, text=text, cursor="hand2", font=self._font(11, "bold"))
            label.grid(row=0, column=column, padx=(0, 16))
            label.bind("<Button-1>", lambda _e, k=key: self._show_tab(k))
            self._tab_labels[key] = label
        self._chat = self._textbox(console.content, 13)
        self._log = self._textbox(console.content, 11)
        for widget in (self._chat, self._log):
            widget.grid(row=0, column=0, sticky="nsew")
        self._configure_chat_tags()
        for level, color in theme.LOG_LEVEL_COLORS.items():
            self._log.tag_config(str(level), foreground=color)
        self._show_tab("chat")

        command_bar = HudPanel(center, self._mono, None, fit=True, pad=12)
        command_bar.grid(row=1, column=0, sticky="ew", padx=gap, pady=(gap, outer))
        command_bar.content.grid_columnconfigure(0, weight=1)
        self._entry = ctk.CTkEntry(
            command_bar.content, height=42, justify="center", border_width=1, border_color=theme.PANEL_ALT,
            placeholder_text=theme.track("Aguardando comando") + "  …",
            fg_color=theme.PANEL, text_color=theme.TEXT, placeholder_text_color=theme.MUTED,
            font=self._font(12),
        )
        self._entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self._mic_btn = self._hud_button(command_bar.content, "◉  OUVIR", self._on_listen, width=118)
        self._mic_btn.configure(state="disabled")
        self._mic_btn.grid(row=0, column=1, padx=(0, 8))
        self._hud_button(command_bar.content, "ENVIAR  ›", self._on_submit, width=118, primary=True).grid(
            row=0, column=2)
        command_bar.refit()

        # ---- coluna direita
        temporal = HudPanel(right, self._mono, "Protocolo Temporal", fit=True)
        temporal.grid(row=0, column=0, sticky="new", padx=(gap, outer), pady=(outer, gap))
        self._calendar = CalendarCanvas(temporal.content, self._mono)
        self._calendar.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(temporal.content, text=theme.track("Sessão"), anchor="w", text_color=theme.MUTED,
                     font=self._font(9)).grid(row=1, column=0, sticky="w", pady=(10, 8))
        self._stat_rows = {}
        for row, (key, label) in enumerate(
            (("count", "COMANDOS"), ("latency", "LATÊNCIA MÉDIA"), ("uptime", "TEMPO ATIVO")), start=2
        ):
            stat = ListRow(temporal.content, self._mono, label, "--")
            stat.grid(row=row, column=0, sticky="ew", pady=(0, 6))
            self._stat_rows[key] = stat
        self._calendar.tick(datetime.now())
        temporal.refit()

        trace = HudPanel(right, self._mono, "Neural Trace")
        trace.grid(row=1, column=0, sticky="nsew", padx=(gap, outer), pady=(gap, outer))
        right.grid_rowconfigure(1, weight=1)
        trace.content.grid_rowconfigure(0, weight=1)
        self._trace = NeuralTrace(trace.content)
        self._trace.grid(row=0, column=0, sticky="nsew")
        self._activity_label = ctk.CTkLabel(trace.content, text="", anchor="w", text_color=theme.MUTED,
                                            font=self._font(9))
        self._activity_label.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self._set_activity(Activity.IDLE)

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=theme.HEADER_BG, corner_radius=0)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_columnconfigure(1, weight=1)
        ctk.CTkFrame(footer, height=1, fg_color=theme.BORDER, corner_radius=0).grid(
            row=0, column=0, columnspan=3, sticky="ew")
        try:
            os_name = platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
        except OSError:
            os_name = platform.system()
        info = f"PYTHON {platform.python_version()}  ·  KERNEL {platform.release().split('-')[0]}  ·  {os_name.upper()}"
        ctk.CTkLabel(footer, text=info, text_color=theme.MUTED, font=self._font(9)).grid(
            row=1, column=0, sticky="w", padx=28, pady=10)
        self._system_label = ctk.CTkLabel(footer, text="", text_color=theme.MUTED, font=self._font(9))
        self._system_label.grid(row=1, column=2, sticky="e", padx=28, pady=10)
        self._refresh_system_label()

    def _hud_button(self, master, text: str, command, *, width: int = 140, primary: bool = False) -> ctk.CTkButton:
        return ctk.CTkButton(
            master, text=text, command=command, width=width, height=40, corner_radius=2,
            font=self._font(11, "bold"),
            fg_color=theme.TEXT if primary else theme.PANEL_ALT,
            hover_color=theme.TEXT_DIM if primary else theme.BORDER,
            text_color=theme.BG if primary else theme.TEXT,
            text_color_disabled=theme.MUTED,
            border_width=0 if primary else 1, border_color=theme.BORDER,
        )

    def _textbox(self, master, size: int) -> ctk.CTkTextbox:
        box = ctk.CTkTextbox(master, fg_color=theme.PANEL, border_width=0, corner_radius=0,
                             text_color=theme.TEXT_DIM, wrap="word", font=self._font(size),
                             scrollbar_button_color=theme.BORDER, scrollbar_button_hover_color=theme.MUTED)
        box.configure(state="disabled")
        return box

    def _configure_chat_tags(self) -> None:
        # Tags configuradas no tk.Text interno: o CTkTextbox proíbe 'font' em tags,
        # e as linhas de respiro dos blocos precisam de fonte pequena.
        text = self._chat._textbox
        block = dict(background=theme.PANEL_ALT, lmargin1=16, lmargin2=16, rmargin=16,
                     lmargincolor=theme.PANEL_ALT, rmargincolor=theme.PANEL_ALT)
        text.tag_configure("block", **block)
        text.tag_configure("pad", font=(self._mono, -8))
        text.tag_configure("gap", font=(self._mono, -10))
        text.tag_configure("author_user", foreground=theme.LISTEN, font=(self._mono, -12, "bold"))
        text.tag_configure("author_delsin", foreground=theme.TEXT, font=(self._mono, -12, "bold"))
        text.tag_configure("author_system", foreground=theme.WARN, font=(self._mono, -12, "bold"))
        text.tag_configure("meta", foreground=theme.MUTED, font=(self._mono, -11))
        text.tag_configure("body", foreground=theme.TEXT_DIM)
        text.tag_configure("failed", foreground=theme.ERROR)

    def _bind_keys(self) -> None:
        self._entry.bind("<Return>", lambda _e: self._on_submit())
        self.bind("<Control-space>", lambda _e: self._on_listen())

    # ================================================================ ações

    def _on_submit(self) -> None:
        text = self._entry.get().strip()
        if text:
            self._entry.delete(0, "end")
            self._cb.on_submit(text)

    def _on_listen(self) -> None:
        if self._stt_ready and self._mic_btn.cget("state") == "normal":
            self._cb.on_listen()

    def _on_voice_switch(self) -> None:
        self._cb.on_toggle_voice(bool(self._voice_switch.get()))

    def _show_tab(self, key: str) -> None:
        self._active_tab = key
        (self._chat if key == "chat" else self._log).tkraise()
        for name, label in self._tab_labels.items():
            label.configure(text_color=theme.TEXT if name == key else theme.MUTED)

    def _toggle_log(self) -> None:
        self._show_tab("chat" if self._active_tab == "log" else "log")

    def open_voice_settings(self) -> None:
        if self._voice_dialog is not None and self._voice_dialog.winfo_exists():
            self._voice_dialog.lift()
            self._voice_dialog.focus_force()
            return
        self._voice_dialog = VoiceDialog(
            self, self._mono, self._cb.get_voice_catalog(),
            VoiceDialogCallbacks(self._cb.on_preview_voice, self._cb.on_save_voice, self._cb.on_install_voice),
        )

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self._cb.on_close()
        finally:
            self.destroy()

    # ================================================================ filas (main thread)

    def _drain_queues(self) -> None:
        if self._closing:
            return
        for _ in range(MAX_ITEMS_PER_TICK):
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            self._apply_event(event)
        lines: list[LogItem] = []
        for _ in range(MAX_ITEMS_PER_TICK):
            try:
                lines.append(self._logs.get_nowait())
            except queue.Empty:
                break
        if lines:
            self._append_logs(lines)
        self.after(POLL_MS, self._drain_queues)

    def _apply_event(self, event: UiEvent) -> None:
        match event:
            case StatusEvent():
                self._apply_status(event)
            case MessageEvent():
                self._append_message(event)
            case ActivityEvent():
                self._set_activity(event.activity)
            case MetricsEvent():
                self._apply_metrics(event)
            case VoiceCatalogEvent():
                if self._voice_dialog is not None and self._voice_dialog.winfo_exists():
                    self._voice_dialog.update_catalog(event.catalog, event.message)

    def _apply_status(self, event: StatusEvent) -> None:
        self._module_states[event.module] = event.state
        row = self._status_rows.get(event.module)
        if row:
            row.set_state(event.state, event.detail)
        if event.module == "stt":
            self._stt_ready = event.state in (ModuleState.ONLINE, ModuleState.ACTIVE)
            listening = event.state is ModuleState.ACTIVE
            self._mic_btn.configure(
                state="normal" if event.state is ModuleState.ONLINE else "disabled",
                text="●  OUVINDO" if listening else "◉  OUVIR",
                border_color=theme.LISTEN if listening else theme.BORDER,
            )
        elif event.module == "tts" and event.state is ModuleState.ONLINE:
            self._voice_switch.configure(state="normal")
        self._refresh_system_label()

    def _apply_metrics(self, event: MetricsEvent) -> None:
        for metric in event.metrics:
            row = self._metric_rows.get(metric.key)
            if row:
                row.set(metric.fraction, metric.display)
            if metric.key == "cpu":
                self._load_segments.set(metric.fraction)

    def _set_activity(self, activity: Activity) -> None:
        self._trace.activity = activity
        self._activity_label.configure(
            text=theme.track("Estado neural") + "   ·   " + self.ACTIVITY_TEXT[activity],
            text_color=theme.ACTIVITY_COLORS[activity] if activity is not Activity.IDLE else theme.MUTED,
        )

    def _append_message(self, event: MessageEvent) -> None:
        authors = {"user": "VOCÊ", "delsin": "DELSIN", "system": "SISTEMA"}
        stamp = datetime.now().strftime("%H:%M:%S")
        meta = f"   {stamp}" + (f"  ·  {event.meta}" if event.meta else "")
        text = self._chat._textbox
        self._chat.configure(state="normal")
        self._message_seq += 1
        mark = f"msg{self._message_seq}"
        text.mark_set(mark, "end-1c")
        text.mark_gravity(mark, "left")
        self._message_marks.append(mark)
        text.insert("end", "\n", ("block", "pad"))
        text.insert("end", authors.get(event.author, event.author.upper()), ("block", f"author_{event.author}"))
        text.insert("end", meta + "\n", ("block", "meta"))
        text.insert("end", event.text + "\n", ("block", "failed" if event.failed else "body"))
        text.insert("end", "\n", ("block", "pad"))
        text.insert("end", "\n", ("gap",))
        if len(self._message_marks) > MAX_CHAT_MESSAGES:
            # Remove as 50 mensagens mais antigas inteiras (nunca corta uma no meio).
            for _ in range(50):
                text.mark_unset(self._message_marks.popleft())
            text.delete("1.0", self._message_marks[0])
        self._chat.configure(state="disabled")
        self._chat.see("end")
        if event.latency_ms is not None:
            self._latencies.append(event.latency_ms)
            self._stat_rows["count"].set(str(len(self._latencies)))
            average = sum(self._latencies) / len(self._latencies)
            self._stat_rows["latency"].set(f"{average:.0f} ms")

    def _append_logs(self, lines: list[LogItem]) -> None:
        self._log.configure(state="normal")
        for level, text in lines:
            self._log.insert("end", text + "\n", str(level))
        overflow = int(self._log.index("end-1c").split(".")[0]) - MAX_LOG_LINES
        if overflow > 0:
            self._log.delete("1.0", f"{overflow + 1}.0")
        self._log.configure(state="disabled")
        self._log.see("end")

    def _refresh_system_label(self) -> None:
        degraded = any(state is ModuleState.ERROR for state in self._module_states.values())
        status = "Operando com restrições" if degraded else "Sistema operacional"
        self._system_label.configure(
            text=theme.track(f"{self._app_name} OS v{self._version}") + "   /   " + theme.track(status),
            text_color=theme.WARN if degraded else theme.MUTED,
        )

    def _tick_clock(self) -> None:
        if self._closing:
            return
        self._calendar.tick(datetime.now())
        elapsed = int(time.monotonic() - self._started)
        self._stat_rows["uptime"].set(f"{elapsed // 3600:02d}:{elapsed % 3600 // 60:02d}:{elapsed % 60:02d}")
        self.after(1000, self._tick_clock)
