"""Mapping of Checkmk perfdata metric names to Home Assistant sensor metadata.

Checkmk's perfdata format (``name=value[unit][;warn;crit;min;max]``) omits the
unit for almost every metric - the actual units live in Checkmk's internal
metric registry, which is not exposed via the REST API. This catalog mirrors
the most common metric definitions so the resulting Home Assistant sensors
display with the right unit, get the matching device class for unit conversion
("63.7 %", "10.2 GB" rather than raw 10953379840), and feed long-term
statistics correctly.

For unknown metric names ``CheckmkMetricSensor`` falls back to the unit that
the perfdata token itself carries (e.g. ``foo=42%``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)


@dataclass(frozen=True, kw_only=True)
class MetricSpec:
    """Describes how a single Checkmk metric should appear in Home Assistant."""

    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT


_PCT = MetricSpec(unit=PERCENTAGE)
_BYTES = MetricSpec(
    unit=UnitOfInformation.BYTES,
    device_class=SensorDeviceClass.DATA_SIZE,
)
# Checkmk reports filesystem sizes pre-converted to MiB.
_MIB = MetricSpec(
    unit=UnitOfInformation.MEBIBYTES,
    device_class=SensorDeviceClass.DATA_SIZE,
)
_BYTES_PER_SECOND = MetricSpec(
    unit=UnitOfDataRate.BYTES_PER_SECOND,
    device_class=SensorDeviceClass.DATA_RATE,
)
_SECONDS = MetricSpec(
    unit=UnitOfTime.SECONDS,
    device_class=SensorDeviceClass.DURATION,
)
_COUNTER = MetricSpec()  # plain number, "measurement" state class only

METRIC_SPECS: Final[dict[str, MetricSpec]] = {
    # CPU
    "util": _PCT,
    "user": _PCT,
    "system": _PCT,
    "privileged": _PCT,
    "iowait": _PCT,
    "idle": _PCT,
    "steal": _PCT,
    # Load average
    "load1": _COUNTER,
    "load5": _COUNTER,
    "load15": _COUNTER,
    # Memory and pagefile
    "mem_used": _BYTES,
    "mem_free": _BYTES,
    "mem_total": _BYTES,
    "mem_used_percent": _PCT,
    "pagefile_used": _BYTES,
    "pagefile_free": _BYTES,
    "pagefile_used_percent": _PCT,
    "percent": _PCT,
    # Filesystem (Checkmk's perfdata for fs_* is in MiB)
    "fs_size": _MIB,
    "fs_used": _MIB,
    "fs_free": _MIB,
    "fs_used_percent": _PCT,
    "growth": _MIB,
    "trend": _MIB,
    # Disk I/O
    "disk_read_throughput": _BYTES_PER_SECOND,
    "disk_write_throughput": _BYTES_PER_SECOND,
    "disk_latency": _SECONDS,
    "disk_average_read_wait": _SECONDS,
    "disk_average_write_wait": _SECONDS,
    "disk_read_ios": _COUNTER,
    "disk_write_ios": _COUNTER,
    "disk_read_ql": _COUNTER,
    "disk_write_ql": _COUNTER,
    # Network interface
    "in": _BYTES_PER_SECOND,
    "out": _BYTES_PER_SECOND,
    "inucast": _COUNTER,
    "outucast": _COUNTER,
    "innucast": _COUNTER,
    "outnucast": _COUNTER,
    "inerr": _COUNTER,
    "outerr": _COUNTER,
    "indisc": _COUNTER,
    "outdisc": _COUNTER,
    "outqlen": _COUNTER,
    # Durations
    "uptime": _SECONDS,
    "execution_time": _SECONDS,
    "cmk_time_agent": _SECONDS,
    "user_time": _SECONDS,
    "system_time": _SECONDS,
    "children_user_time": _SECONDS,
    "children_system_time": _SECONDS,
    "offset": _SECONDS,
    # Temperature (Checkmk delivers Celsius unless an explicit unit is in perfdata)
    "temp": MetricSpec(
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    "temperature": MetricSpec(
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
}
