"""Descoberta das entradas de áudio (microfones) via PipeWire."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess

from config.voice_profile import InputOption

log = logging.getLogger("delsin.voice.devices")


def pipewire_capture_available() -> bool:
    return bool(shutil.which("pw-record") and shutil.which("pw-dump"))


def list_inputs(timeout_s: float = 3.0) -> list[InputOption]:
    """Microfones conhecidos pelo PipeWire, com o padrão do sistema marcado."""
    try:
        raw = subprocess.run(["pw-dump"], capture_output=True, timeout=timeout_s, check=True).stdout
        objects = json.loads(raw)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        log.warning("Não foi possível listar microfones: %s", exc)
        return []
    default = _default_source(objects)
    inputs = []
    for obj in objects:
        props = (obj.get("info") or {}).get("props") or {}
        if props.get("media.class") != "Audio/Source" or "node.name" not in props:
            continue
        name = props["node.name"]
        label = props.get("node.description") or props.get("node.nick") or name
        inputs.append(InputOption(name, label, name == default))
    return sorted(inputs, key=lambda option: (not option.is_default, option.label))


def _default_source(objects: list[dict]) -> str | None:
    for obj in objects:
        if obj.get("type") != "PipeWire:Interface:Metadata":
            continue
        if ((obj.get("props") or {}).get("metadata.name")) != "default":
            continue
        for entry in obj.get("metadata") or []:
            if entry.get("key") != "default.audio.source":
                continue
            value = entry.get("value")
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    return value
            if isinstance(value, dict):
                return value.get("name")
    return None
