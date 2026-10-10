"""Componentes visuais do HUD.

Tk não tem transparência entre widgets. Para o quadriculado de fundo parecer
contínuo, cada superfície (GridSurface) desenha o próprio trecho do grid
alinhado pela posição dela na janela.
"""
from __future__ import annotations

import calendar
import math
import tkinter as tk
from datetime import date, datetime

import customtkinter as ctk

from gui import theme
from gui.events import Activity, ModuleState

MONTHS = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
          "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")
WEEKDAY_INITIALS = ("D", "S", "T", "Q", "Q", "S", "S")


def draw_grid(canvas: tk.Canvas, width: int, height: int, ox: int, oy: int, tag: str) -> None:
    step = theme.GRID_STEP
    x = -(ox % step)
    while x < width:
        canvas.create_line(x, 0, x, height, fill=theme.GRID, tags=tag)
        x += step
    y = -(oy % step)
    while y < height:
        canvas.create_line(0, y, width, y, fill=theme.GRID, tags=tag)
        y += step


class GridSurface(tk.Canvas):
    """Canvas com o quadriculado do fundo, alinhado à janela."""

    def __init__(self, master, **kwargs) -> None:
        kwargs.setdefault("bg", theme.BG)
        super().__init__(master, highlightthickness=0, bd=0, **kwargs)
        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<Map>", self._redraw, add="+")

    def _offset(self) -> tuple[int, int]:
        top = self.winfo_toplevel()
        return self.winfo_rootx() - top.winfo_rootx(), self.winfo_rooty() - top.winfo_rooty()

    def _redraw(self, _event=None) -> None:
        self.delete("grid")
        draw_grid(self, self.winfo_width(), self.winfo_height(), *self._offset(), "grid")
        self.tag_lower("grid")


class HudPanel(GridSurface):
    """Painel com borda fina, cantoneiras e título espaçado (estilo HUD)."""

    MARGIN = 7
    BRACKET = 16

    def __init__(self, master, mono: str, title: str | None = None, *, fit: bool = False, pad: int = 18) -> None:
        super().__init__(master, width=200, height=80)
        self._fit = fit
        self.body = ctk.CTkFrame(self, fg_color=theme.PANEL, corner_radius=0)
        self.body.grid_columnconfigure(0, weight=1)
        self._window = self.create_window(0, 0, window=self.body, anchor="nw")

        row = 0
        if title is not None:
            self.header = ctk.CTkFrame(self.body, fg_color="transparent")
            self.header.grid(row=0, column=0, sticky="ew", padx=pad, pady=(pad, 0))
            self.header.grid_columnconfigure(0, weight=1)
            self.title_label = ctk.CTkLabel(self.header, text=theme.track(title), anchor="w",
                                            text_color=theme.TEXT, font=ctk.CTkFont(mono, 12, "bold"))
            self.title_label.grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(self.header, text="━━ ▪", text_color=theme.MUTED,
                         font=ctk.CTkFont(mono, 10)).grid(row=0, column=9, sticky="e")
            ctk.CTkFrame(self.body, height=1, fg_color=theme.BORDER).grid(
                row=1, column=0, sticky="ew", padx=pad, pady=(12, 0))
            row = 2
        self.content = ctk.CTkFrame(self.body, fg_color="transparent")
        self.content.grid(row=row, column=0, sticky="nsew", padx=pad,
                          pady=(14 if title is not None else pad, pad))
        self.content.grid_columnconfigure(0, weight=1)
        self.body.grid_rowconfigure(row, weight=1)

    def refit(self) -> None:
        """Ajusta a altura do painel ao conteúdo (painéis de altura natural)."""
        self.update_idletasks()
        self.configure(height=self.body.winfo_reqheight() + 2 * (self.MARGIN + 1))

    def _redraw(self, _event=None) -> None:
        super()._redraw()
        w, h, m, length = self.winfo_width(), self.winfo_height(), self.MARGIN, self.BRACKET
        if w < 4 * m or h < 4 * m:
            return
        self.delete("frame")
        self.create_rectangle(m, m, w - m - 1, h - m - 1, outline=theme.BORDER, tags="frame")
        o, r, b = m - 4, w - 1 - (m - 4), h - 1 - (m - 4)
        for points in (
            (o, o + length, o, o, o + length, o),
            (r - length, o, r, o, r, o + length),
            (o, b - length, o, b, o + length, b),
            (r - length, b, r, b, r, b - length),
        ):
            self.create_line(*points, fill=theme.BRACKET, width=2, capstyle="projecting", tags="frame")
        self.coords(self._window, m + 1, m + 1)
        self.itemconfigure(self._window, width=w - 2 * m - 2, height=h - 2 * m - 2)


class MetricRow(ctk.CTkFrame):
    def __init__(self, master, mono: str, icon: str, label: str) -> None:
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=icon, width=20, text_color=theme.MUTED,
                     font=ctk.CTkFont(mono, 13)).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkLabel(self, text=label.upper(), anchor="w", text_color=theme.TEXT_DIM,
                     font=ctk.CTkFont(mono, 11)).grid(row=0, column=1, sticky="w")
        self._bar = ctk.CTkProgressBar(self, width=80, height=3, corner_radius=0, border_width=0,
                                       fg_color=theme.BAR_BG, progress_color=theme.BAR_FG)
        self._bar.set(0)
        self._bar.grid(row=0, column=2, padx=12)
        self._value = ctk.CTkLabel(self, text="--", width=58, anchor="e", text_color=theme.TEXT,
                                   font=ctk.CTkFont(mono, 11, "bold"))
        self._value.grid(row=0, column=3)

    def set(self, fraction: float, display: str) -> None:
        color = theme.ERROR if fraction >= 0.95 else theme.WARN if fraction >= 0.85 else theme.BAR_FG
        self._bar.configure(progress_color=color)
        self._bar.set(min(max(fraction, 0.0), 1.0))
        self._value.configure(text=display)


class ListRow(ctk.CTkFrame):
    """Linha com faixa lateral (estilo 'upcoming protocols')."""

    def __init__(self, master, mono: str, label: str, value: str = "") -> None:
        super().__init__(master, fg_color=theme.PANEL_ALT, corner_radius=0, height=1)
        self.grid_columnconfigure(1, weight=1)
        self._strip = ctk.CTkFrame(self, width=2, height=1, corner_radius=0, fg_color=theme.BORDER)
        self._strip.grid(row=0, column=0, rowspan=2, sticky="ns")
        self._label = ctk.CTkLabel(self, text=label, anchor="w", text_color=theme.TEXT,
                                   font=ctk.CTkFont(mono, 11, "bold"))
        self._label.grid(row=0, column=1, sticky="w", padx=(12, 6), pady=(9, 9))
        self._value = ctk.CTkLabel(self, text=value, anchor="e", text_color=theme.TEXT_DIM,
                                   font=ctk.CTkFont(mono, 11))
        self._value.grid(row=0, column=2, sticky="e", padx=(6, 12))
        self._detail = ctk.CTkLabel(self, text="", anchor="w", justify="left", text_color=theme.MUTED,
                                    font=ctk.CTkFont(mono, 10), wraplength=300)

    def set(self, value: str, color: str | None = None, detail: str | None = None) -> None:
        self._value.configure(text=value, text_color=color or theme.TEXT_DIM)
        if color:
            self._strip.configure(fg_color=color)
        if detail:
            self._label.grid_configure(pady=(9, 0))
            self._detail.configure(text=detail)
            self._detail.grid(row=1, column=1, columnspan=2, sticky="ew", padx=12, pady=(2, 9))
        elif detail is not None:
            self._label.grid_configure(pady=(9, 9))
            self._detail.grid_remove()


class ModuleRow(ListRow):
    def set_state(self, state: ModuleState, detail: str) -> None:
        self.set(state.value.upper(), theme.STATE_COLORS[state], detail)


class CalendarCanvas(tk.Canvas):
    GAP = 6
    CELL_H = 30
    TOP = 44

    def __init__(self, master, mono: str) -> None:
        super().__init__(master, bg=theme.PANEL, highlightthickness=0, height=self.TOP + 22 + 6 * 36)
        self._mono = mono
        self._date: date | None = None
        self.bind("<Configure>", lambda _e: self._draw())

    def tick(self, now: datetime) -> None:
        if now.date() != self._date:
            self._date = now.date()
            self._draw()
        self.itemconfigure("clock", text=f"HORA DO SISTEMA: {now:%H:%M:%S}")

    def _draw(self) -> None:
        width = self.winfo_width()
        if width < 100:
            return
        today = self._date or date.today()
        self.delete("all")
        self.create_text(0, 12, anchor="w", text=f"{MONTHS[today.month - 1]} {today.year}",
                         fill=theme.TEXT, font=(self._mono, -15, "bold"))
        self.create_text(width, 12, anchor="e", text="", fill=theme.MUTED,
                         font=(self._mono, -10), tags="clock")
        gap, cell_h = self.GAP, self.CELL_H
        cell_w = (width - 6 * gap) / 7
        for col, initial in enumerate(WEEKDAY_INITIALS):
            self.create_text(col * (cell_w + gap) + cell_w / 2, self.TOP, text=initial,
                             fill=theme.MUTED, font=(self._mono, -10))
        first_col = (today.replace(day=1).weekday() + 1) % 7  # domingo primeiro
        days = calendar.monthrange(today.year, today.month)[1]
        for day in range(1, days + 1):
            row, col = divmod(first_col + day - 1, 7)
            x = col * (cell_w + gap)
            y = self.TOP + 16 + row * (cell_h + gap)
            is_today = day == today.day
            self.create_rectangle(x, y, x + cell_w, y + cell_h, fill=theme.PANEL_ALT,
                                  outline=theme.BRACKET if is_today else theme.PANEL_ALT,
                                  width=2 if is_today else 1)
            self.create_text(x + cell_w / 2, y + cell_h / 2, text=str(day),
                             fill=theme.TEXT if is_today else theme.TEXT_DIM,
                             font=(self._mono, -12, "bold" if is_today else "normal"))
        rows = math.ceil((first_col + days) / 7)
        needed = self.TOP + 16 + rows * (cell_h + gap)
        if int(self.cget("height")) != needed:
            self.configure(height=needed)


class NeuralTrace(tk.Canvas):
    """Visualização animada do estado do assistente (ocioso/ouvindo/processando/falando)."""

    FRAME_MS = 33
    POINTS = 72

    def __init__(self, master) -> None:
        super().__init__(master, bg=theme.PANEL_ALT, highlightthickness=1,
                         highlightbackground=theme.BORDER, height=200)
        self.activity = Activity.IDLE
        self._phase = 0.0
        self._level = 0.0
        self._items: dict[str, int] = {}
        self._ripples: list[int] = []
        self.bind("<Configure>", self._build)
        self.after(self.FRAME_MS, self._tick)

    def _build(self, _event=None) -> None:
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        draw_grid(self, w, h, 0, 0, "grid")
        self._cx, self._cy, self._width = w / 2, h / 2, w
        self._base = max(min(w, h) * 0.15, 12)
        flat = [coord for i in range(self.POINTS) for coord in (i * w / (self.POINTS - 1), self._cy)]
        self._items = {
            "wave": self.create_line(*flat, fill=theme.TEXT_DIM, width=1, smooth=True),
            "outer": self.create_oval(0, 0, 0, 0, outline=theme.TEXT_DIM, dash=(3, 5)),
            "mid": self.create_oval(0, 0, 0, 0, outline=theme.MUTED),
            "inner": self.create_oval(0, 0, 0, 0, outline=theme.TEXT, width=2),
            "core": self.create_oval(0, 0, 0, 0, fill=theme.TEXT, outline=""),
        }
        self._ripples = [self.create_oval(0, 0, 0, 0, outline=theme.BRACKET, state="hidden") for _ in range(3)]
        self._circle("outer", self._base * 1.9)
        self._circle("mid", self._base * 1.4)
        self._circle("inner", self._base)

    def _circle(self, key_or_id: str | int, radius: float) -> None:
        item = self._items[key_or_id] if isinstance(key_or_id, str) else key_or_id
        self.coords(item, self._cx - radius, self._cy - radius, self._cx + radius, self._cy + radius)

    def _tick(self) -> None:
        try:
            self._animate()
            self.after(self.FRAME_MS if self.activity is not Activity.IDLE else self.FRAME_MS * 2, self._tick)
        except tk.TclError:
            pass  # widget destruído no fechamento

    def _animate(self) -> None:
        if not self._items:
            return
        step = self.FRAME_MS / 1000 * (1 if self.activity is not Activity.IDLE else 2)
        self._phase += step
        t, base, activity = self._phase, self._base, self.activity
        color = theme.ACTIVITY_COLORS[activity]
        target = {Activity.IDLE: 0.0, Activity.LISTENING: 0.25,
                  Activity.PROCESSING: 0.12, Activity.SPEAKING: 1.0}[activity]
        self._level += (target - self._level) * 0.18

        core = base * 0.24 * (1 + 0.12 * math.sin(t * 2.2) + 0.6 * self._level * abs(math.sin(t * 11)))
        self._circle("core", core)
        self.itemconfigure(self._items["core"], fill=color)
        self.itemconfigure(self._items["inner"], outline=theme.blend(theme.TEXT, color, 0.7))
        spin = 40 if activity is Activity.PROCESSING else 6
        self.itemconfigure(self._items["outer"], dashoffset=int(t * spin) % 8)

        amplitude = self._level * base * 1.2
        points = []
        for i in range(self.POINTS):
            x = i * self._width / (self.POINTS - 1)
            dx = (x - self._cx) / (self._width / 2)
            envelope = math.exp(-dx * dx * 2.5)
            wave = 0.6 * math.sin(x * 0.09 + t * 14) + 0.4 * math.sin(x * 0.21 - t * 9)
            points += (x, self._cy + amplitude * envelope * wave)
        self.coords(self._items["wave"], *points)
        self.itemconfigure(self._items["wave"], fill=theme.blend(theme.MUTED, color, min(self._level * 2, 1)))

        for index, ripple in enumerate(self._ripples):
            if activity is Activity.LISTENING:
                progress = (t * 0.7 + index / 3) % 1
                self._circle(ripple, base * (1 + progress * 1.3))
                self.itemconfigure(ripple, state="normal", outline=theme.blend(color, theme.PANEL_ALT, progress))
            else:
                self.itemconfigure(ripple, state="hidden")


class Avatar(tk.Canvas):
    def __init__(self, master, size: int = 58) -> None:
        super().__init__(master, width=size, height=size, bg=theme.HEADER_BG, highlightthickness=0)
        c, r = size / 2, size / 2 - 2
        self.create_oval(c - r, c - r, c + r, c + r, outline=theme.MUTED, dash=(2, 3))
        r2 = r - 6
        self.create_oval(c - r2, c - r2, c + r2, c + r2, outline=theme.BRACKET, width=2)
        self.create_oval(c - 5, c - 11, c + 5, c - 1, outline=theme.TEXT, width=2)
        self.create_arc(c - 10, c + 1, c + 10, c + 19, start=0, extent=180, style="arc",
                        outline=theme.TEXT, width=2)


class LoadSegments(tk.Canvas):
    COUNT = 5

    def __init__(self, master) -> None:
        super().__init__(master, width=self.COUNT * 20, height=5, bg=theme.HEADER_BG, highlightthickness=0)
        self._segments = [self.create_rectangle(i * 20, 0, i * 20 + 16, 5, fill=theme.BAR_BG, outline="")
                          for i in range(self.COUNT)]

    def set(self, fraction: float) -> None:
        lit = max(1, math.ceil(fraction * self.COUNT))
        for index, segment in enumerate(self._segments):
            self.itemconfigure(segment, fill=theme.TEXT if index < lit else theme.BAR_BG)
