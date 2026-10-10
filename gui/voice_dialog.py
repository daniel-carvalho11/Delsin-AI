"""Janela de configuração de voz: motor, voz, tom, velocidade e volume."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import customtkinter as ctk

from config.voice_profile import (
    PITCH_RANGE, RATE_RANGE, VOLUME_RANGE, VoiceCatalog, VoiceOption, VoiceProfile,
)
from gui import theme

SAMPLE_TEXT = "Delsin online. Sistemas verificados. Aguardando instruções."


@dataclass(frozen=True)
class VoiceDialogCallbacks:
    on_preview: Callable[[VoiceProfile, str], None]
    on_save: Callable[[VoiceProfile], None]
    on_install: Callable[[str, str], None]


class VoiceDialog(ctk.CTkToplevel):
    def __init__(self, master, mono: str, catalog: VoiceCatalog, callbacks: VoiceDialogCallbacks) -> None:
        super().__init__(master, fg_color=theme.PANEL)
        self._mono, self._cb, self._catalog = mono, callbacks, catalog
        self.title("Delsin · configuração de voz")
        self.geometry("600x580")
        self.minsize(560, 560)
        self.transient(master)
        self.grid_columnconfigure(0, weight=1)

        profile = catalog.profile
        self._engine = profile.engine
        self._voice_id = profile.voice
        self._options: list[VoiceOption] = []

        ctk.CTkLabel(self, text=theme.track("Configuração de voz"), anchor="w", text_color=theme.TEXT,
                     font=ctk.CTkFont(mono, 13, "bold")).grid(row=0, column=0, sticky="ew", padx=28, pady=(26, 4))
        ctk.CTkLabel(self, text="As mudanças valem para todas as respostas após SALVAR.", anchor="w",
                     text_color=theme.MUTED, font=ctk.CTkFont(mono, 11)).grid(row=1, column=0, sticky="ew", padx=28)
        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER).grid(row=2, column=0, sticky="ew", padx=28, pady=16)

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=3, column=0, sticky="nsew", padx=28)
        form.grid_columnconfigure(1, weight=1)

        available = [e for e in catalog.engines if e.available]
        self._engine_labels = {e.label: e.name for e in available}
        self._section(form, 0, "Motor")
        self._engine_switch = ctk.CTkSegmentedButton(
            form, values=list(self._engine_labels), command=self._on_engine,
            font=ctk.CTkFont(mono, 11), selected_color=theme.BORDER, selected_hover_color=theme.MUTED,
            unselected_color=theme.PANEL_ALT, fg_color=theme.PANEL_ALT, text_color=theme.TEXT,
        )
        self._engine_switch.grid(row=0, column=1, columnspan=2, sticky="ew", pady=6)
        missing = [f"{e.label}: {e.detail}" for e in catalog.engines if not e.available]
        if missing:
            ctk.CTkLabel(form, text="\n".join(missing), anchor="w", justify="left", text_color=theme.WARN,
                         font=ctk.CTkFont(mono, 10)).grid(row=1, column=1, columnspan=2, sticky="ew")

        self._section(form, 2, "Voz")
        self._voice_menu = ctk.CTkOptionMenu(
            form, values=["-"], command=self._on_voice, font=ctk.CTkFont(mono, 11),
            dropdown_font=ctk.CTkFont(mono, 11), fg_color=theme.PANEL_ALT, button_color=theme.BORDER,
            button_hover_color=theme.MUTED, text_color=theme.TEXT,
        )
        self._voice_menu.grid(row=2, column=1, columnspan=2, sticky="ew", pady=6)
        self._install_btn = self._button(form, "BAIXAR VOZ", self._install, primary=False)
        self._install_btn.grid(row=3, column=1, columnspan=2, sticky="ew", pady=(0, 6))

        self._rate = self._slider(form, 4, "Velocidade", RATE_RANGE, profile.rate, lambda v: f"{v:.2f}×")
        self._pitch = self._slider(form, 5, "Tom", PITCH_RANGE, profile.pitch, lambda v: f"{(v - 1) * 100:+.0f}%")
        self._volume = self._slider(form, 6, "Volume", VOLUME_RANGE, profile.volume, lambda v: f"{v * 100:.0f}%")

        self._section(form, 7, "Frase")
        self._sample = ctk.CTkEntry(form, fg_color=theme.PANEL_ALT, border_color=theme.BORDER,
                                    text_color=theme.TEXT, font=ctk.CTkFont(mono, 11))
        self._sample.insert(0, SAMPLE_TEXT)
        self._sample.grid(row=7, column=1, columnspan=2, sticky="ew", pady=6)

        self._status = ctk.CTkLabel(self, text="", anchor="w", text_color=theme.TEXT_DIM,
                                    font=ctk.CTkFont(mono, 11), wraplength=520, justify="left")
        self._status.grid(row=4, column=0, sticky="ew", padx=28, pady=(14, 0))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=5, column=0, sticky="ew", padx=28, pady=(14, 26))
        actions.grid_columnconfigure(0, weight=1)
        self._button(actions, "FECHAR", self.destroy, primary=False).grid(row=0, column=1, padx=(0, 10))
        self._button(actions, "TESTAR", self._test, primary=False).grid(row=0, column=2, padx=(0, 10))
        self._button(actions, "SALVAR", self._save, primary=True).grid(row=0, column=3)

        engine_label = next((lbl for lbl, name in self._engine_labels.items() if name == self._engine), None)
        if engine_label:
            self._engine_switch.set(engine_label)
        self._fill_voices()
        self.after(150, self._focus)

    # ---------- construção ----------

    def _section(self, master, row: int, text: str) -> None:
        ctk.CTkLabel(master, text=text.upper(), anchor="w", width=120, text_color=theme.MUTED,
                     font=ctk.CTkFont(self._mono, 10, "bold")).grid(row=row, column=0, sticky="w", pady=6)

    def _button(self, master, text: str, command, *, primary: bool) -> ctk.CTkButton:
        return ctk.CTkButton(
            master, text=text, command=command, height=36, corner_radius=2,
            font=ctk.CTkFont(self._mono, 11, "bold"),
            fg_color=theme.TEXT if primary else theme.PANEL_ALT,
            hover_color=theme.TEXT_DIM if primary else theme.BORDER,
            text_color=theme.BG if primary else theme.TEXT,
            border_width=0 if primary else 1, border_color=theme.BORDER,
        )

    def _slider(self, master, row, label, bounds, value, fmt) -> ctk.CTkSlider:
        self._section(master, row, label)
        low, high = bounds
        readout = ctk.CTkLabel(master, text=fmt(value), width=64, anchor="e", text_color=theme.TEXT,
                               font=ctk.CTkFont(self._mono, 11, "bold"))
        readout.grid(row=row, column=2, sticky="e")
        slider = ctk.CTkSlider(
            master, from_=low, to=high, number_of_steps=round((high - low) / 0.05),
            command=lambda v: readout.configure(text=fmt(v)),
            button_color=theme.TEXT, button_hover_color=theme.TEXT_DIM,
            progress_color=theme.TEXT_DIM, fg_color=theme.BAR_BG,
        )
        slider.set(value)
        slider.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=8)
        return slider

    def _focus(self) -> None:
        self.lift()
        self.focus_force()

    # ---------- estado ----------

    def _fill_voices(self) -> None:
        self._options = list(self._catalog.voices.get(self._engine, ()))
        if not self._options:
            self._voice_menu.configure(values=["(nenhuma voz)"])
            self._voice_menu.set("(nenhuma voz)")
            self._refresh_install()
            return
        labels = [self._label(o) for o in self._options]
        self._voice_menu.configure(values=labels)
        current = next((o for o in self._options if o.id == self._voice_id), None)
        if current is None:
            current = next((o for o in self._options if o.installed), self._options[0])
            self._voice_id = current.id
        self._voice_menu.set(self._label(current))
        self._refresh_install()

    @staticmethod
    def _label(option: VoiceOption) -> str:
        return option.label if option.installed else f"{option.label}  [não instalada]"

    def _selected(self) -> VoiceOption | None:
        return next((o for o in self._options if o.id == self._voice_id), None)

    def _refresh_install(self) -> None:
        option = self._selected()
        if option and not option.installed:
            self._install_btn.configure(text=f"BAIXAR VOZ · {option.size_mb} MB", state="normal")
            self._install_btn.grid()
        else:
            self._install_btn.grid_remove()

    def _profile(self) -> VoiceProfile:
        return VoiceProfile(self._engine, self._voice_id, self._rate.get(),
                            self._pitch.get(), self._volume.get()).clamped()

    def _ready(self) -> bool:
        option = self._selected()
        if option is None:
            self._set_status("Selecione uma voz.", theme.WARN)
            return False
        if not option.installed:
            self._set_status("Essa voz ainda não está instalada. Use BAIXAR VOZ primeiro.", theme.WARN)
            return False
        return True

    def _set_status(self, text: str, color: str = theme.TEXT_DIM) -> None:
        self._status.configure(text=text, text_color=color)

    # ---------- ações ----------

    def _on_engine(self, label: str) -> None:
        self._engine = self._engine_labels[label]
        self._voice_id = ""
        self._fill_voices()

    def _on_voice(self, label: str) -> None:
        option = next((o for o in self._options if self._label(o) == label), None)
        if option:
            self._voice_id = option.id
        self._refresh_install()

    def _test(self) -> None:
        if self._ready():
            self._cb.on_preview(self._profile(), self._sample.get().strip() or SAMPLE_TEXT)
            self._set_status("Reproduzindo amostra…")

    def _save(self) -> None:
        if self._ready():
            self._cb.on_save(self._profile())
            self._set_status("Perfil salvo e aplicado.", theme.OK)

    def _install(self) -> None:
        option = self._selected()
        if option is None:
            return
        self._install_btn.configure(text="BAIXANDO…", state="disabled")
        self._set_status(f"Baixando {option.label} ({option.size_mb} MB)… pode levar alguns minutos.")
        self._cb.on_install(option.engine, option.id)

    def update_catalog(self, catalog: VoiceCatalog, message: str) -> None:
        self._catalog = catalog
        self._fill_voices()
        if message:
            failed = message.lower().startswith("falha")
            self._set_status(message, theme.ERROR if failed else theme.OK)
