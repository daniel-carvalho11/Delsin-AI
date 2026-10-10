"""Silencia o handler de erros do ALSA.

Ao abrir o PyAudio, a libasound tenta todos os PCMs do alsa.conf e despeja
dezenas de "ALSA lib pcm.c ... Unknown PCM" no stderr. É ruído inofensivo,
mas polui o terminal e esconde erros reais.
"""
from __future__ import annotations

import ctypes
import ctypes.util

_HANDLER_TYPE = ctypes.CFUNCTYPE(
    None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p
)
# Referência global obrigatória: se o GC coletar o callback, o C chama
# um ponteiro inválido e o processo leva segfault.
_noop_handler = _HANDLER_TYPE(lambda *_: None)
_installed = False


def silence_alsa_errors() -> bool:
    global _installed
    if _installed:
        return True
    lib_path = ctypes.util.find_library("asound")
    if not lib_path:
        return False
    try:
        ctypes.cdll.LoadLibrary(lib_path).snd_lib_error_set_handler(_noop_handler)
    except (OSError, AttributeError):
        return False
    _installed = True
    return True
