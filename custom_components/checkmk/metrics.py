"""Mapping of Checkmk perfdata metric names to Home Assistant sensor metadata.

Checkmk's perfdata format (``name=value[unit][;warn;crit;min;max]``) omits the
unit for almost every metric - the actual units live in Checkmk's separate
metric registry which is not exposed via the REST API. ``METRIC_SPECS`` mirrors
the common metric definitions so the resulting Home Assistant sensors get the
right unit, device class and long-term-statistics behaviour.

A separate visibility policy decides where each sensor shows up in the HA UI:

  - **Primary** (no entity category, enabled): dashboard-relevant metrics, kept
    intentionally short - one host should not flood the main view with 50
    entities.
  - **Diagnostic visible** (``EntityCategory.DIAGNOSTIC``, enabled): useful
    detail data, tucked into the "Diagnose" section of the device.
  - **Diagnostic hidden** (``EntityCategory.DIAGNOSTIC``, disabled by default):
    the long tail of low-level Linux / kernel / TCP / per-packet counters that
    most users never need. Still created in the entity registry so a curious
    user can enable them one by one.

Unknown metric names (anything not in any of these lists) default to the
"diagnostic hidden" tier - safer than dumping arbitrary perfdata into the
dashboard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
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


# --- Reusable specs --------------------------------------------------------

_PCT = MetricSpec(unit=PERCENTAGE)
_BYTES = MetricSpec(
    unit=UnitOfInformation.BYTES,
    device_class=SensorDeviceClass.DATA_SIZE,
)
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
_RATE = MetricSpec()  # plain number, semantically "per second" but unitless in HA
_COUNT = MetricSpec()


METRIC_SPECS: Final[dict[str, MetricSpec]] = {
    # ----- CPU & load --------------------------------------------------------
    "util": _PCT,
    "user": _PCT,
    "system": _PCT,
    "privileged": _PCT,
    "iowait": _PCT,
    "wait": _PCT,
    "idle": _PCT,
    "steal": _PCT,
    "load1": _COUNT,
    "load5": _COUNT,
    "load15": _COUNT,
    # ----- Memory / pagefile / swap -----------------------------------------
    "mem_used": _BYTES,
    "mem_free": _BYTES,
    "mem_total": _BYTES,
    "mem_available": _BYTES,
    "mem_used_percent": _PCT,
    "pagefile_used": _BYTES,
    "pagefile_free": _BYTES,
    "pagefile_used_percent": _PCT,
    "percent": _PCT,
    "swap_used": _BYTES,
    "swap_free": _BYTES,
    "swap_total": _BYTES,
    "swap_cached": _BYTES,
    "total_total": _BYTES,
    "total_used": _BYTES,
    # ----- Memory: deep Linux breakdown (all bytes) -------------------------
    "active": _BYTES,
    "active_anon": _BYTES,
    "active_file": _BYTES,
    "inactive": _BYTES,
    "inactive_anon": _BYTES,
    "inactive_file": _BYTES,
    "anon_pages": _BYTES,
    "anon_huge_pages": _BYTES,
    "bounce": _BYTES,
    "buffers": _BYTES,
    "cached": _BYTES,
    "caches": _BYTES,
    "commit_limit": _BYTES,
    "dirty": _BYTES,
    "file_huge_pages": _BYTES,
    "file_pmd_mapped": _BYTES,
    "hardware_corrupted": _BYTES,
    "kernel_stack": _BYTES,
    "kreclaimable": _BYTES,
    "mapped": _BYTES,
    "mem_lnx_committed_as": _BYTES,
    "mem_lnx_page_tables": _BYTES,
    "mem_lnx_shmem": _BYTES,
    "mlocked": _BYTES,
    "nfs_unstable": _BYTES,
    "pending": _BYTES,
    "percpu": _BYTES,
    "sec_page_tables": _BYTES,
    "shmem_huge_pages": _BYTES,
    "shmem_pmd_mapped": _BYTES,
    "slab": _BYTES,
    "sreclaimable": _BYTES,
    "sunreclaim": _BYTES,
    "unaccepted": _BYTES,
    "unevictable": _BYTES,
    "writeback": _BYTES,
    "writeback_tmp": _BYTES,
    "zswap": _BYTES,
    "zswapped": _BYTES,
    # ----- Filesystem (Checkmk reports fs_* in MiB) --------------------------
    "fs_size": _MIB,
    "fs_used": _MIB,
    "fs_free": _MIB,
    "fs_used_percent": _PCT,
    "growth": _MIB,
    "trend": _MIB,
    "inodes_used": _COUNT,
    # ----- Disk I/O ---------------------------------------------------------
    "disk_read_throughput": _BYTES_PER_SECOND,
    "disk_write_throughput": _BYTES_PER_SECOND,
    "disk_latency": _SECONDS,
    "disk_utilization": _PCT,
    "disk_average_wait": _SECONDS,
    "disk_average_read_wait": _SECONDS,
    "disk_average_write_wait": _SECONDS,
    "disk_average_request_size": _BYTES,
    "disk_average_read_request_size": _BYTES,
    "disk_average_write_request_size": _BYTES,
    "disk_queue_length": _COUNT,
    "disk_read_ios": _RATE,
    "disk_write_ios": _RATE,
    "disk_read_ql": _COUNT,
    "disk_write_ql": _COUNT,
    # ----- Network interface ------------------------------------------------
    "in": _BYTES_PER_SECOND,
    "out": _BYTES_PER_SECOND,
    "inucast": _RATE,
    "outucast": _RATE,
    "innucast": _RATE,
    "outnucast": _RATE,
    "inmcast": _RATE,
    "outmcast": _RATE,
    "inbcast": _RATE,
    "outbcast": _RATE,
    "inerr": _RATE,
    "outerr": _RATE,
    "indisc": _RATE,
    "outdisc": _RATE,
    "outqlen": _COUNT,
    # ----- Kernel / process -------------------------------------------------
    "context_switches": _RATE,
    "process_creations": _RATE,
    "major_page_faults": _RATE,
    "page_swap_in": _RATE,
    "page_swap_out": _RATE,
    "threads": _COUNT,
    "thread_usage": _PCT,
    # ----- Time / sync ------------------------------------------------------
    "uptime": _SECONDS,
    "execution_time": _SECONDS,
    "cmk_time_agent": _SECONDS,
    "user_time": _SECONDS,
    "system_time": _SECONDS,
    "children_user_time": _SECONDS,
    "children_system_time": _SECONDS,
    "offset": _SECONDS,
    "time_offset": _SECONDS,
    "jitter": _SECONDS,
    "last_sync_time": _SECONDS,
    "last_sync_receive_time": _SECONDS,
    # ----- TCP connection states (all counts) -------------------------------
    "ESTABLISHED": _COUNT,
    "LISTEN": _COUNT,
    "TIME_WAIT": _COUNT,
    "CLOSE_WAIT": _COUNT,
    "CLOSED": _COUNT,
    "CLOSING": _COUNT,
    "FIN_WAIT1": _COUNT,
    "FIN_WAIT2": _COUNT,
    "LAST_ACK": _COUNT,
    "SYN_RECV": _COUNT,
    "SYN_SENT": _COUNT,
    # ----- Temperature ------------------------------------------------------
    "temp": MetricSpec(
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    "temperature": MetricSpec(
        unit=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
}


# --- Visibility policy -----------------------------------------------------
#
# Three tiers, looked up by metric name in priority order. Anything that falls
# through ends up in the "hidden diagnostic" bucket.

PRIMARY_METRICS: Final[frozenset[str]] = frozenset(
    {
        "util",
        "mem_used_percent",
        "fs_used_percent",
        "load1",
        "in",
        "out",
        "uptime",
        "mem_used",
        "fs_used",
    }
)

DIAGNOSTIC_VISIBLE_METRICS: Final[frozenset[str]] = frozenset(
    {
        # Disk I/O - genuinely unique signal, not duplicated elsewhere.
        "disk_read_throughput",
        "disk_write_throughput",
        "disk_latency",
        "disk_utilization",
        # Memory pressure indicators that the primary tier doesn't cover.
        "mem_available",
        "swap_used",
        "pagefile_used_percent",
    }
)


def visibility_for(metric: str) -> tuple[EntityCategory | None, bool]:
    """Return ``(entity_category, enabled_by_default)`` for a metric name.

    Unknown / unlisted metrics land in the hidden-diagnostic tier so the
    default dashboard stays clean regardless of how exotic a Checkmk plugin's
    perfdata gets.
    """
    if metric in PRIMARY_METRICS:
        return (None, True)
    if metric in DIAGNOSTIC_VISIBLE_METRICS:
        return (EntityCategory.DIAGNOSTIC, True)
    return (EntityCategory.DIAGNOSTIC, False)
