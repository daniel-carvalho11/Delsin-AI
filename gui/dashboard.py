"""Painel de controle do Delsin (customtkinter).

A janela é "burra": não conhece Agent, STT nem TTS. Recebe callbacks para
ações do usuário e consome duas filas (eventos de UI e logs) no próprio loop.
"""
from __future__ import annotations

import queue
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import customtkinter as ctk

from core.logger import LogItem
from gui import theme
from gui.events import MessageEvent, ModuleState, StatusEvent, UiEvent

POLL_MS = 50
MAX_ITEMS_PER_TICK = 200
MAX_LOG_LINES = 1500


@dataclass(frozen=True)
class DashboardCallbacks:
    on_submit: Callable[[str], None]
    on_listen: Callable[[], None]
    on_toggle_voice: Callable[[bool], None]
    on_close: Callable[[], None]


class _StatusRow(ctk.CTkFrame):
    def __init__(self, master, label: str, sans: str) -> None:
        super().__init__(master, fg_color=theme.PANEL_ALT, corner_radius=8,
                         border_width=1, border_color=theme.BORDER)
        self.grid_columnconfigure(1, weight=1)
        self._dot = ctk.CTkLabel(self, text="●", width=18, text_color=theme.MUTED,
                                 font=ctk.CTkFont(sans, 14))
        self._dot.grid(row=0, column=0, rowspan=2, padx=(10, 4), pady=8)
        ctk.CTkLabel(self, text=label, anchor="w", text_color=theme.TEXT,
                     font=ctk.CTkFont(sans, 13, "bold")).grid(row=0, column=1, sticky="ew", pady=(8, 0))
        self._state = ctk.CTkLabel(self, text="offline", anchor="w", text_color=theme.MUTED,
                                   font=ctk.CTkFont(sans, 11), wraplength=190, justify="left")
        self._state.grid(row=1, column=1, sticky="ew", pady=(0, 8), padx=(0, 10))

    def set(self, state: ModuleState, detail: str) -> None:
        color = theme.STATE_COLORS[state]
        self._dot.configure(text_color=color)
        self._state.configure(text=f"{state.value} · {detail}" if detail else state.value,
                              text_color=color if state is ModuleState.ERROR else theme.MUTED)


class Dashboard(ctk.CTk):
    MODULES = {
        "core": "Núcleo (Core)",
        "skills": "Skills",
        "stt": "Microfone (STT)",
        "tts": "Voz (TTS)",
        "llm": "IA / LLM",
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
        self._closing = False
        self._stt_ready = False

        self.title(f"{app_name} · painel de controle")
        self.geometry("1180x760")
        self.minsize(900, 600)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self._sans, self._mono = theme.pick_fonts()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar(app_name, version)
        self._build_main()
        self._bind_keys()

        self.after(POLL_MS, self._drain_queues)
        self._tick_clock()
        self._entry.focus_set()

    # ---------------- layout ----------------

    def _build_sidebar(self, app_name: str, version: str) -> None:
        bar = ctk.CTkFrame(self, width=270, fg_color=theme.PANEL, corner_radius=0)
        bar.grid(row=0, column=0, sticky="nsw")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(bar, text=app_name.upper(), text_color=theme.ACCENT,
                     font=ctk.CTkFont(self._sans, 30, "bold")).grid(row=0, column=0, padx=20, pady=(26, 0), sticky="w")
        ctk.CTkLabel(bar, text="assistente analítico modular", text_color=theme.MUTED,
                     font=ctk.CTkFont(self._sans, 12)).grid(row=1, column=0, padx=20, sticky="w")
        ctk.CTkFrame(bar, height=1, fg_color=theme.BORDER).grid(row=2, column=0, sticky="ew", padx=20, pady=18)
        ctk.CTkLabel(bar, text="MÓDULOS", text_color=theme.MUTED,
                     font=ctk.CTkFont(self._sans, 11, "bold")).grid(row=3, column=0, padx=20, sticky="w")

        self._status_rows: dict[str, _StatusRow] = {}
        for i, (key, label) in enumerate(self.MODULES.items()):
            row = _StatusRow(bar, label, self._sans)
            row.grid(row=4 + i, column=0, sticky="ew", padx=16, pady=4)
            self._status_rows[key] = row

        bar.grid_rowconfigure(20, weight=1)
        self._voice_switch = ctk.CTkSwitch(
            bar, text="Responder por voz", command=self._on_voice_switch,
            progress_color=theme.ACCENT, text_color=theme.TEXT, font=ctk.CTkFont(self._sans, 12),
        )
        self._voice_switch.grid(row=21, column=0, padx=20, pady=(0, 10), sticky="w")
        self._voice_switch.configure(state="disabled")
        ctk.CTkLabel(bar, text=f"v{version}  ·  Enter envia · Ctrl+Espaço ouve",
                     text_color=theme.MUTED, font=ctk.CTkFont(self._sans, 10)).grid(
            row=22, column=0, padx=20, pady=(0, 16), sticky="w")

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color=theme.BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=18, pady=16)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=3)
        main.grid_rowconfigure(3, weight=2)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Console", text_color=theme.TEXT,
                     font=ctk.CTkFont(self._sans, 18, "bold")).grid(row=0, column=0, sticky="w")
        self._clock = ctk.CTkLabel(header, text="", text_color=theme.MUTED,
                                   font=ctk.CTkFont(self._mono, 13))
        self._clock.grid(row=0, column=1, sticky="e")

        self._chat = self._textbox(main, self._sans, 14)
        self._chat.grid(row=1, column=0, sticky="nsew")
        self._chat.tag_config("user", foreground=theme.ACCENT)
        self._chat.tag_config("delsin", foreground=theme.OK)
        self._chat.tag_config("system", foreground=theme.WARN)
        self._chat.tag_config("meta", foreground=theme.MUTED)
        self._chat.tag_config("body", foreground=theme.TEXT)
        self._chat.tag_config("failed", foreground=theme.ERROR)

        ctk.CTkLabel(main, text="LOG DE SISTEMA", text_color=theme.MUTED,
                     font=ctk.CTkFont(self._sans, 11, "bold")).grid(row=2, column=0, sticky="w", pady=(12, 4))
        self._log = self._textbox(main, self._mono, 12)
        self._log.grid(row=3, column=0, sticky="nsew")
        for level, color in theme.LOG_LEVEL_COLORS.items():
            self._log.tag_config(str(level), foreground=color)

        bar = ctk.CTkFrame(main, fg_color=theme.PANEL, corner_radius=10,
                           border_width=1, border_color=theme.BORDER)
        bar.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        bar.grid_columnconfigure(0, weight=1)
        self._entry = ctk.CTkEntry(
            bar, placeholder_text="Digite um comando para o Delsin…", height=40,
            fg_color=theme.PANEL_ALT, border_color=theme.BORDER, text_color=theme.TEXT,
            font=ctk.CTkFont(self._sans, 14),
        )
        self._entry.grid(row=0, column=0, sticky="ew", padx=(10, 6), pady=10)
        self._mic_btn = ctk.CTkButton(
            bar, text="🎙  Ouvir", width=110, height=40, state="disabled",
            fg_color=theme.ACCENT_DIM, hover_color=theme.ACCENT_HOVER, text_color=theme.TEXT,
            font=ctk.CTkFont(self._sans, 13, "bold"), command=self._on_listen,
        )
        self._mic_btn.grid(row=0, column=1, padx=6, pady=10)
        ctk.CTkButton(
            bar, text="Enviar", width=100, height=40, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER, text_color=theme.BG,
            font=ctk.CTkFont(self._sans, 13, "bold"), command=self._on_submit,
        ).grid(row=0, column=2, padx=(6, 10), pady=10)

    def _textbox(self, master, family: str, size: int) -> ctk.CTkTextbox:
        box = ctk.CTkTextbox(master, fg_color=theme.PANEL, border_width=1, border_color=theme.BORDER,
                             corner_radius=10, text_color=theme.TEXT, wrap="word",
                             font=ctk.CTkFont(family, size))
        box.configure(state="disabled")
        return box

    def _bind_keys(self) -> None:
        self._entry.bind("<Return>", lambda _e: self._on_submit())
        self.bind("<Control-space>", lambda _e: self._on_listen())

    # ---------------- ações do usuário ----------------

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

    def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self._cb.on_close()
        finally:
            self.destroy()

    # ---------------- consumo das filas (main thread) ----------------

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
        if isinstance(event, StatusEvent):
            self._apply_status(event)
        elif isinstance(event, MessageEvent):
            self._append_message(event)

    def _apply_status(self, event: StatusEvent) -> None:
        row = self._status_rows.get(event.module)
        if row:
            row.set(event.state, event.detail)
        if event.module == "stt":
            self._stt_ready = event.state in (ModuleState.ONLINE, ModuleState.ACTIVE)
            listening = event.state is ModuleState.ACTIVE
            self._mic_btn.configure(
                state="normal" if event.state is ModuleState.ONLINE else "disabled",
                text="●  Ouvindo" if listening else "🎙  Ouvir",
                fg_color=theme.LISTEN if listening else theme.ACCENT_DIM,
            )
        elif event.module == "tts" and event.state is ModuleState.ONLINE:
            self._voice_switch.configure(state="normal")

    def _append_message(self, event: MessageEvent) -> None:
        labels = {"user": "Você", "delsin": "Delsin", "system": "Sistema"}
        stamp = datetime.now().strftime("%H:%M:%S")
        body_tag = "failed" if event.meta.startswith("falha") else "body"
        self._chat.configure(state="normal")
        self._chat.insert("end", labels.get(event.author, event.author), event.author)
        self._chat.insert("end", f"  {stamp}{'  ·  ' + event.meta if event.meta else ''}\n", "meta")
        self._chat.insert("end", f"{event.text}\n\n", body_tag)
        self._chat.configure(state="disabled")
        self._chat.see("end")

    def _append_logs(self, lines: list[LogItem]) -> None:
        self._log.configure(state="normal")
        for level, text in lines:
            self._log.insert("end", text + "\n", str(level))
        overflow = int(self._log.index("end-1c").split(".")[0]) - MAX_LOG_LINES
        if overflow > 0:
            self._log.delete("1.0", f"{overflow + 1}.0")
        self._log.configure(state="disabled")
        self._log.see("end")

    def _tick_clock(self) -> None:
        if not self._closing:
            self._clock.configure(text=datetime.now().strftime("%d/%m/%Y  %H:%M:%S"))
            self.after(1000, self._tick_clock)
