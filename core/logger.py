"""Logging com três destinos: arquivo rotativo, terminal e fila para a GUI.

A GUI nunca é chamada direto de threads de trabalho (Tkinter não é
thread-safe); ela drena esta fila no próprio loop de eventos.
"""
from __future__ import annotations

import logging
import queue
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LogItem = tuple[int, str]

_FORMAT = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s"
_GUI_FORMAT = "%(asctime)s  %(levelname)-7s %(message)s"


class GuiQueueHandler(logging.Handler):
    def __init__(self, target: queue.Queue[LogItem]) -> None:
        super().__init__()
        self._target = target

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._target.put_nowait((record.levelno, self.format(record)))
        except queue.Full:
            pass  # descartar é preferível a bloquear o produtor
        except Exception:
            self.handleError(record)


def setup_logging(log_dir: Path, debug: bool = False) -> queue.Queue[LogItem]:
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger("delsin")
    root.setLevel(level)
    root.propagate = False

    gui_queue: queue.Queue[LogItem] = queue.Queue(maxsize=2000)

    file_handler = RotatingFileHandler(
        log_dir / "delsin.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(logging.Formatter(_FORMAT, "%H:%M:%S"))

    gui_handler = GuiQueueHandler(gui_queue)
    gui_handler.setFormatter(logging.Formatter(_GUI_FORMAT, "%H:%M:%S"))

    root.handlers[:] = [file_handler, console_handler, gui_handler]
    return gui_queue
