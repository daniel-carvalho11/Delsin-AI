"""Integrações (servidores MCP) que o Claude do Delsin pode usar.

O arquivo ~/.config/delsin/mcp.json é GERADO a partir das chaves salvas em
secrets.env (fora do repositório) e passado ao Claude Code com
--strict-mcp-config: só estas integrações existem para o Delsin.

Política de aprovação (aplicada em main._approve):
- leitura (buscar, listar, obter, consultar) roda direto;
- qualquer escrita (enviar, criar, editar, apagar) mostra o cartão de aprovação.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

_READ = re.compile(r"(get|retrieve|list|search|query|read|fetch|find|download|self|users?$)", re.IGNORECASE)
_WRITE = re.compile(r"(send|create|delete|update|patch|append|move|trash|modify|draft|write|remove|"
                    r"archive|label|insert|upload|share|post-page|reply|forward|batch)", re.IGNORECASE)


def is_read_only(tool: str) -> bool:
    """mcp__notion__API-post-search -> True; mcp__gmail__send_gmail_message -> False."""
    if not tool.startswith("mcp__"):
        return False
    name = tool.split("__", 2)[-1]
    return bool(_READ.search(name)) and not _WRITE.search(name.replace("post-search", "search"))


def build_servers(get_secret: Callable[[str], str | None]) -> dict[str, dict]:
    servers: dict[str, dict] = {}
    notion = get_secret("NOTION_TOKEN")
    if notion and shutil.which("npx"):
        servers["notion"] = {
            "command": "npx", "args": ["-y", "@notionhq/notion-mcp-server@2.5.2"],
            "env": {"NOTION_TOKEN": notion},
        }
    return servers


def write_mcp_config(path: Path, get_secret: Callable[[str], str | None]) -> list[str]:
    """Regera o mcp.json (permissão 0600). Retorna os nomes das integrações ativas."""
    servers = build_servers(get_secret)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".mcp-")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"mcpServers": servers}, handle, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return sorted(servers)
