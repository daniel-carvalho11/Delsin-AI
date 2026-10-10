"""Paleta e tipografia do painel."""
from __future__ import annotations

import logging
import tkinter.font as tkfont

from gui.events import ModuleState

BG = "#0a0e13"
PANEL = "#10161e"
PANEL_ALT = "#0d1218"
BORDER = "#1e2a37"
ACCENT = "#00d1ff"
ACCENT_HOVER = "#00a3c7"
ACCENT_DIM = "#0b3a4a"
TEXT = "#d6e0ea"
MUTED = "#6a7b8c"
OK = "#2ee59d"
WARN = "#ffb547"
ERROR = "#ff5c6c"
LISTEN = "#b48cff"

STATE_COLORS = {
    ModuleState.OFFLINE: MUTED,
    ModuleState.STARTING: WARN,
    ModuleState.ONLINE: OK,
    ModuleState.ACTIVE: LISTEN,
    ModuleState.ERROR: ERROR,
}

LOG_LEVEL_COLORS = {
    logging.DEBUG: MUTED,
    logging.INFO: "#8fa3b8",
    logging.WARNING: WARN,
    logging.ERROR: ERROR,
    logging.CRITICAL: ERROR,
}

_SANS = ("Inter", "Cantarell", "Noto Sans", "DejaVu Sans")
_MONO = ("JetBrains Mono", "Fira Code", "Adwaita Mono", "Noto Sans Mono", "DejaVu Sans Mono")


def pick_fonts() -> tuple[str, str]:
    """Escolhe a primeira fonte instalada. Requer a janela Tk já criada."""
    available = set(tkfont.families())
    sans = next((f for f in _SANS if f in available), "TkDefaultFont")
    mono = next((f for f in _MONO if f in available), "TkFixedFont")
    return sans, mono
