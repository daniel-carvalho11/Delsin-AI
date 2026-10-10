"""Skills básicas: relógio, diagnóstico do sistema e ajuda."""
from __future__ import annotations

import os
import platform
from datetime import datetime
from pathlib import Path

from core.contracts import Request, Response, SkillContext
from skills._base import KeywordSkill, strip_accents

_WEEKDAYS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
             "sexta-feira", "sábado", "domingo")


class ClockSkill(KeywordSkill):
    name = "clock"
    description = "Informa hora e data locais."
    keywords = ("hora", "horas", "horario", "data", "que dia", "hoje")

    def handle(self, request: Request, context: SkillContext) -> Response:
        now = datetime.now()
        text = strip_accents(request.normalized)
        if "data" in text or "dia" in text or "hoje" in text:
            return Response(f"Hoje é {_WEEKDAYS[now.weekday()]}, {now:%d/%m/%Y}.", self.name)
        return Response(f"Agora são {now:%H:%M}.", self.name)


class SystemStatusSkill(KeywordSkill):
    name = "system_status"
    description = "Diagnóstico rápido: carga de CPU, memória e kernel."
    keywords = ("status", "diagnostico", "sistema", "memoria", "cpu")

    def handle(self, request: Request, context: SkillContext) -> Response:
        load1, load5, _ = os.getloadavg()
        cpus = os.cpu_count() or 1
        mem = self._meminfo()
        parts = [f"Carga {load1:.2f} (1 min) / {load5:.2f} (5 min) em {cpus} núcleos."]
        if mem:
            total, available = mem
            used_pct = 100 * (1 - available / total)
            parts.append(f"Memória em uso: {used_pct:.0f}% de {total / 1024**2:.1f} GiB.")
        parts.append(f"Kernel {platform.release()}.")
        if load1 > cpus:
            parts.append("Atenção: carga acima do número de núcleos.")
        return Response(" ".join(parts), self.name)

    @staticmethod
    def _meminfo() -> tuple[int, int] | None:
        """Retorna (total_kib, disponível_kib) lendo /proc/meminfo."""
        try:
            fields = {}
            for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
                key, value = line.split(":", 1)
                fields[key] = int(value.split()[0])
            return fields["MemTotal"], fields["MemAvailable"]
        except (OSError, KeyError, ValueError):
            return None


class HelpSkill(KeywordSkill):
    name = "help"
    description = "Lista as skills disponíveis."
    keywords = ("ajuda", "help", "comandos", "o que voce faz", "skills")

    def handle(self, request: Request, context: SkillContext) -> Response:
        skills = sorted(context.list_skills(), key=lambda s: s.name)
        lines = [f"• {s.name}: {s.description}" for s in skills]
        return Response(
            "Skills ativas:\n" + "\n".join(lines),
            self.name,
            speak=False,  # listas longas são ruins de ouvir
        )
