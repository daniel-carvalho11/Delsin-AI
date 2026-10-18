"""Janela de integrações (Notion, Google) do cérebro Claude."""
from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from gui import theme

TONE_COLORS = {"ok": theme.OK, "warn": theme.WARN, "error": theme.ERROR, "info": theme.TEXT_DIM}

NOTION_STEPS = (
    "1. notion.so/profile/integrations → Nova integração → tipo Interna → copie o 'Internal Integration Secret'.\n"
    "2. Em cada página/banco que o Delsin pode ver: ••• → Conexões → adicione a integração.\n"
    "3. Cole o token abaixo e clique em SALVAR. O Delsin reinicia a sessão do Claude com o Notion."
)
GOOGLE_NOTE = (
    "Gmail, Agenda e Classroom exigem um cliente OAuth do Google Cloud criado por você "
    "(passo a passo no README, seção 2.3). Assim que existir, o Delsin passa a oferecer os serviços aqui."
)


class IntegrationsDialog(ctk.CTkToplevel):
    def __init__(self, master, mono: str, active: list[str], on_save: Callable[[str, str], None]) -> None:
        super().__init__(master, fg_color=theme.PANEL)
        self._mono, self._on_save = mono, on_save
        self.title("Delsin · integrações")
        self.geometry("720x560")
        self.minsize(640, 520)
        self.transient(master)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text=theme.track("Integrações"), anchor="w", text_color=theme.TEXT,
                     font=ctk.CTkFont(mono, 13, "bold")).grid(row=0, column=0, sticky="ew", padx=28, pady=(26, 4))
        ctk.CTkLabel(self, text="Leituras rodam direto; enviar, criar, editar ou apagar sempre pede sua aprovação.",
                     anchor="w", text_color=theme.MUTED, font=ctk.CTkFont(mono, 11)).grid(
            row=1, column=0, sticky="ew", padx=28)
        self._active = ctk.CTkLabel(self, text="", anchor="w", text_color=theme.TEXT_DIM, font=ctk.CTkFont(mono, 11))
        self._active.grid(row=2, column=0, sticky="ew", padx=28, pady=(10, 0))
        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER).grid(row=3, column=0, sticky="ew", padx=28, pady=16)

        ctk.CTkLabel(self, text="NOTION", anchor="w", text_color=theme.TEXT,
                     font=ctk.CTkFont(mono, 11, "bold")).grid(row=4, column=0, sticky="ew", padx=28)
        ctk.CTkLabel(self, text=NOTION_STEPS, anchor="w", justify="left", wraplength=640, text_color=theme.MUTED,
                     font=ctk.CTkFont(mono, 10)).grid(row=5, column=0, sticky="ew", padx=28, pady=(6, 8))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=6, column=0, sticky="ew", padx=28)
        row.grid_columnconfigure(0, weight=1)
        self._notion = ctk.CTkEntry(row, show="•", fg_color=theme.PANEL_ALT, border_color=theme.BORDER,
                                    text_color=theme.TEXT, font=ctk.CTkFont(mono, 11), placeholder_text="ntn_…")
        self._notion.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        ctk.CTkButton(row, text="SALVAR", width=110, height=36, corner_radius=2, command=self._save_notion,
                      font=ctk.CTkFont(mono, 11, "bold"), fg_color=theme.TEXT, hover_color=theme.TEXT_DIM,
                      text_color=theme.BG).grid(row=0, column=1)

        ctk.CTkFrame(self, height=1, fg_color=theme.BORDER).grid(row=7, column=0, sticky="ew", padx=28, pady=16)
        ctk.CTkLabel(self, text="GOOGLE · GMAIL · AGENDA · CLASSROOM", anchor="w", text_color=theme.TEXT,
                     font=ctk.CTkFont(mono, 11, "bold")).grid(row=8, column=0, sticky="ew", padx=28)
        ctk.CTkLabel(self, text=GOOGLE_NOTE, anchor="w", justify="left", wraplength=640, text_color=theme.MUTED,
                     font=ctk.CTkFont(mono, 10)).grid(row=9, column=0, sticky="ew", padx=28, pady=(6, 0))

        self._status = ctk.CTkLabel(self, text="", anchor="w", justify="left", wraplength=640,
                                    text_color=theme.TEXT_DIM, font=ctk.CTkFont(mono, 11))
        self._status.grid(row=10, column=0, sticky="ew", padx=28, pady=(18, 24))
        self.update_state(active, "", "info")
        self.after(150, lambda: (self.lift(), self.focus_force()))

    def _save_notion(self) -> None:
        token = self._notion.get().strip()
        if not token:
            self.update_state(None, "Cole o token da integração do Notion.", "warn")
            return
        self._notion.delete(0, "end")
        self.update_state(None, "Salvando e reiniciando a sessão do Claude com o Notion…", "info")
        self._on_save("NOTION_TOKEN", token)

    def update_state(self, active: list[str] | None, message: str, tone: str) -> None:
        if active is not None:
            self._active.configure(text="Ativas: " + (", ".join(active) if active else "nenhuma"))
        if message:
            self._status.configure(text=message, text_color=TONE_COLORS.get(tone, theme.TEXT_DIM))
