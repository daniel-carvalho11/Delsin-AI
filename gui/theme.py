"""Paleta, tipografia e helpers visuais do painel (estilo HUD)."""
from __future__ import annotations

import logging
import tkinter.font as tkfont

from gui.events import Activity, ModuleState

# Base azul-marinho monocromática; cor só para estados.
BG = "#0c1626"
HEADER_BG = "#0a1320"
GRID = "#132137"
PANEL = "#0f1a2c"
PANEL_ALT = "#15233a"
BORDER = "#24344e"
BRACKET = "#b9c6d8"
TEXT = "#e6edf6"
TEXT_DIM = "#a7b4c6"
MUTED = "#5f7391"
BAR_BG = "#25354f"
BAR_FG = "#e6edf6"
OK = "#5fd3a6"
WARN = "#e9b965"
ERROR = "#f07484"
LISTEN = "#8fb4ff"

GRID_STEP = 30

STATE_COLORS = {
    ModuleState.OFFLINE: MUTED,
    ModuleState.STARTING: WARN,
    ModuleState.ONLINE: OK,
    ModuleState.ACTIVE: LISTEN,
    ModuleState.ERROR: ERROR,
}

ACTIVITY_COLORS = {
    Activity.IDLE: BRACKET,
    Activity.LISTENING: LISTEN,
    Activity.PROCESSING: WARN,
    Activity.SPEAKING: OK,
}

LOG_LEVEL_COLORS = {
    logging.DEBUG: MUTED,
    logging.INFO: TEXT_DIM,
    logging.WARNING: WARN,
    logging.ERROR: ERROR,
    logging.CRITICAL: ERROR,
}

_MONO = ("JetBrains Mono", "Fira Code", "Adwaita Mono", "Noto Sans Mono", "Liberation Mono", "DejaVu Sans Mono")


def pick_mono() -> str:
    """Primeira fonte monoespaçada instalada. Requer a janela Tk já criada."""
    available = set(tkfont.families())
    return next((f for f in _MONO if f in available), "TkFixedFont")


def track(text: str) -> str:
    """Simula letter-spacing (Tk não suporta): 'CORE SYSTEMS' -> 'C O R E   S Y S T E M S'."""
    return "   ".join(" ".join(word) for word in text.upper().split())


def blend(color_a: str, color_b: str, t: float) -> str:
    """Interpola duas cores hex (t=0 -> a, t=1 -> b). Usado nas animações."""
    t = min(max(t, 0.0), 1.0)
    a = [int(color_a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(color_b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))
