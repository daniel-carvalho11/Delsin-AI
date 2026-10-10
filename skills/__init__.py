"""Descoberta automática de skills.

Qualquer módulo neste pacote (exceto os iniciados por "_") é importado e toda
subclasse concreta de Skill definida nele é instanciada.

SEGURANÇA: isto executa código de qualquer .py colocado aqui. Mantenha o
diretório sem permissão de escrita para outros usuários (chmod 755 ou 700).
"""
from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil

from core.contracts import Skill

log = logging.getLogger("delsin.skills")


def discover_skills() -> list[Skill]:
    found: list[Skill] = []
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_"):
            continue
        qualified = f"{__name__}.{module_info.name}"
        try:
            module = importlib.import_module(qualified)
        except Exception:
            log.exception("Falha ao importar %s — skill ignorada", qualified)
            continue
        for obj in vars(module).values():
            if (
                inspect.isclass(obj)
                and issubclass(obj, Skill)
                and not inspect.isabstract(obj)
                and obj.__module__ == qualified
            ):
                try:
                    found.append(obj())
                except Exception:
                    log.exception("Falha ao instanciar %s.%s", qualified, obj.__name__)
    return found
