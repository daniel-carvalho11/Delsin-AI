"""Telemetria do host (Linux) lida de /proc e /sys — sem dependências externas.

Cada métrica é independente: se uma fonte não existir (ex.: sem sensor
térmico em VM), ela é omitida em vez de derrubar a amostra inteira.
"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("delsin.services.telemetry")

_THERMAL_ROOT = Path("/sys/class/thermal")
_PREFERRED_SENSORS = ("x86_pkg_temp", "cpu", "acpitz")


@dataclass(frozen=True, slots=True)
class Metric:
    key: str
    label: str
    fraction: float  # 0.0–1.0, para barras
    display: str


class TelemetrySampler:
    def __init__(self, disk_path: Path = Path.home()) -> None:
        self._disk_path = disk_path
        self._prev_cpu: tuple[int, int] | None = None
        self._cpus = os.cpu_count() or 1
        self._sensor = self._find_sensor()

    def sample(self) -> list[Metric]:
        metrics: list[Metric] = []
        for reader in (self._cpu, self._memory, self._disk, self._temperature, self._load):
            try:
                metric = reader()
            except (OSError, ValueError, IndexError, KeyError) as exc:
                log.debug("Métrica %s indisponível: %s", reader.__name__, exc)
                continue
            if metric:
                metrics.append(metric)
        return metrics

    def _cpu(self) -> Metric | None:
        fields = [int(v) for v in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
        idle, total = fields[3] + fields[4], sum(fields)
        previous, self._prev_cpu = self._prev_cpu, (idle, total)
        if previous is None or total == previous[1]:
            return None  # precisa de duas amostras para calcular a variação
        busy = 1 - (idle - previous[0]) / (total - previous[1])
        return Metric("cpu", "Processamento", busy, f"{busy:.0%}")

    def _memory(self) -> Metric:
        info = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            info[key] = int(value.split()[0])
        used = 1 - info["MemAvailable"] / info["MemTotal"]
        return Metric("memory", "Memória", used, f"{used:.0%}")

    def _disk(self) -> Metric:
        usage = shutil.disk_usage(self._disk_path)
        used = usage.used / usage.total
        return Metric("disk", "Disco", used, f"{used:.0%}")

    def _temperature(self) -> Metric | None:
        if not self._sensor:
            return None
        celsius = int(self._sensor.read_text()) / 1000
        return Metric("temp", "Temperatura", min(celsius / 100, 1.0), f"{celsius:.0f}°C")

    def _load(self) -> Metric:
        load1 = os.getloadavg()[0]
        return Metric("load", "Carga média", min(load1 / self._cpus, 1.0), f"{load1:.2f}")

    @staticmethod
    def _find_sensor() -> Path | None:
        zones = {}
        for zone in sorted(_THERMAL_ROOT.glob("thermal_zone*")):
            try:
                zones[(zone / "type").read_text().strip()] = zone / "temp"
            except OSError:
                continue
        for name in _PREFERRED_SENSORS:
            if name in zones:
                return zones[name]
        return next(iter(zones.values()), None)
