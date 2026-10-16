"""Segredos (chaves de API) FORA do repositório.

Ordem de leitura: variável de ambiente > ~/.config/delsin/secrets.env.
O arquivo é criado com permissão 0600 (só o seu usuário lê) numa pasta 0700.
Nunca coloque chaves no código nem em arquivos versionados: o repositório é público.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

_CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
SECRETS_PATH = _CONFIG_HOME / "delsin" / "secrets.env"
_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


def _read_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_secret(name: str, path: Path = SECRETS_PATH) -> str | None:
    return os.environ.get(name) or _read_file(path).get(name) or None


def set_secret(name: str, value: str, path: Path = SECRETS_PATH) -> None:
    if not _NAME.match(name):
        raise ValueError(f"Nome de segredo inválido: {name!r}")
    if any(c in value for c in "\r\n"):
        raise ValueError("O valor não pode conter quebras de linha")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    values = _read_file(path)
    if value:
        values[name] = value
    else:
        values.pop(name, None)
    body = "# Segredos do Delsin — NÃO versionar\n" + "".join(f"{k}={v}\n" for k, v in sorted(values.items()))
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".secrets-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def mask(value: str | None) -> str:
    if not value:
        return "não configurada"
    return f"{value[:4]}…{value[-4:]}" if len(value) > 10 else "configurada"
