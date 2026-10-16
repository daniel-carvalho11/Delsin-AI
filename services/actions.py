"""Execução das ações que o usuário APROVOU no painel.

Só roda o que o modelo pediu, exatamente como pediu (o mesmo texto mostrado
no cartão de confirmação). Ferramentas suportadas: Bash, Write, Edit.

- Bash: `bash -c` em nova sessão de processos, saída em arquivo temporário
  (assim `programa &` não prende o Delsin), timeout com kill do grupo inteiro.
- Write/Edit: apenas dentro da pasta pessoal do usuário.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger("delsin.services.actions")

MAX_OUTPUT_CHARS = 4000


@dataclass(frozen=True, slots=True)
class ActionResult:
    ok: bool
    output: str


class ActionRunner:
    def __init__(self, home: Path = Path.home(), timeout_s: float = 120.0) -> None:
        self._home = home.resolve()
        self._timeout_s = timeout_s

    def run(self, tool: str, data: dict[str, Any]) -> ActionResult:
        try:
            match tool:
                case "Bash":
                    return self._bash(str(data.get("command", "")))
                case "Write":
                    return self._write(str(data.get("file_path", "")), str(data.get("content", "")))
                case "Edit":
                    return self._edit(str(data.get("file_path", "")), str(data.get("old_string", "")),
                                      str(data.get("new_string", "")), bool(data.get("replace_all", False)))
                case _:
                    return ActionResult(False, f"Ferramenta {tool} não suportada pelo executor do Delsin")
        except OSError as exc:
            return ActionResult(False, f"Erro do sistema: {exc}")

    def _bash(self, command: str) -> ActionResult:
        if not command.strip():
            return ActionResult(False, "Comando vazio")
        log.info("Executando comando aprovado: %s", command)
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as out:
            proc = subprocess.Popen(
                ["bash", "-c", command], cwd=self._home, stdin=subprocess.DEVNULL,
                stdout=out, stderr=subprocess.STDOUT, start_new_session=True,
            )
            try:
                code = proc.wait(timeout=self._timeout_s)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                return ActionResult(False, f"Comando excedeu {self._timeout_s:.0f}s e foi encerrado")
            out.seek(0)
            output = out.read()
        if len(output) > MAX_OUTPUT_CHARS:
            output = output[:MAX_OUTPUT_CHARS] + "\n[saída truncada]"
        return ActionResult(code == 0, f"código de saída {code}\n{output}".strip())

    def _inside_home(self, raw_path: str) -> Path:
        path = Path(raw_path).expanduser()
        resolved = (self._home / path if not path.is_absolute() else path).resolve()
        if resolved != self._home and self._home not in resolved.parents:
            raise PermissionError(f"Fora da pasta pessoal: {resolved}")
        return resolved

    def _write(self, raw_path: str, content: str) -> ActionResult:
        try:
            path = self._inside_home(raw_path)
        except PermissionError as exc:
            return ActionResult(False, str(exc))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        log.info("Arquivo escrito (aprovado): %s", path)
        return ActionResult(True, f"Arquivo salvo: {path} ({len(content)} caracteres)")

    def _edit(self, raw_path: str, old: str, new: str, replace_all: bool) -> ActionResult:
        try:
            path = self._inside_home(raw_path)
        except PermissionError as exc:
            return ActionResult(False, str(exc))
        text = path.read_text(encoding="utf-8")
        count = text.count(old) if old else 0
        if count == 0:
            return ActionResult(False, "Trecho a substituir não encontrado no arquivo")
        if count > 1 and not replace_all:
            return ActionResult(False, f"Trecho aparece {count} vezes; edição ambígua")
        path.write_text(text.replace(old, new) if replace_all else text.replace(old, new, 1), encoding="utf-8")
        log.info("Arquivo editado (aprovado): %s", path)
        return ActionResult(True, f"Arquivo editado: {path}")
