"""Sensor platform for the Checkmk integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CONF_URL, PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util, slugify

from . import CheckmkConfigEntry
from .const import (
    CONF_CREATE_METRIC_SENSORS,
    DEFAULT_CREATE_METRIC_SENSORS,
    DOMAIN,
    HOST_STATE,
    SERVICE_STATE,
)
from .coordinator import CheckmkCoordinator
from .parsing import parse_perf_data

# Maps a parsed Checkmk performance-data unit to a Home Assistant unit.
_UNIT_MAP = {"%": PERCENTAGE}


@dataclass(frozen=True, kw_only=True)
class CheckmkSummaryDescription(SensorEntityDescription):
    """Describes a Checkmk site-wide summary sensor."""

    value_fn: Callable[[dict[str, Any]], int]


def _count(items: dict, state: int) -> int:
    """Count entries in ``items`` whose Livestatus ``state`` matches."""
    return sum(1 for entry in items.values() if entry.get("state") == state)


def _problems(data: dict[str, Any]) -> int:
    """Count unhandled problems (no ack, not in a scheduled downtime)."""
    total = 0
    for entry in (*data["hosts"].values(), *data["services"].values()):
        if (
            entry.get("state")
            and not entry.get("acknowledged")
            and not entry.get("scheduled_downtime_depth")
        ):
            total += 1
    return total


SUMMARY_SENSORS: tuple[CheckmkSummaryDescription, ...] = (
    CheckmkSummaryDescription(
        key="hosts_total",
        name="Hosts total",
        icon="mdi:server",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d["hosts"]),
    ),
    CheckmkSummaryDescription(
        key="hosts_down",
        name="Hosts down",
        icon="mdi:server-off",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _count(d["hosts"], 1),
    ),
    CheckmkSummaryDescription(
        key="hosts_unreachable",
        name="Hosts unreachable",
        icon="mdi:server-network-off",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _count(d["hosts"], 2),
    ),
    CheckmkSummaryDescription(
        key="services_total",
        name="Services total",
        icon="mdi:cog",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: len(d["services"]),
    ),
    CheckmkSummaryDescription(
        key="services_warning",
        name="Services warning",
        icon="mdi:alert",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _count(d["services"], 1),
    ),
    CheckmkSummaryDescription(
        key="services_critical",
        name="Services critical",
        icon="mdi:alert-circle",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _count(d["services"], 2),
    ),
    CheckmkSummaryDescription(
        key="services_unknown",
        name="Services unknown",
        icon="mdi:help-circle",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _count(d["services"], 3),
    ),
    CheckmkSummaryDescription(
        key="problems",
        name="Open problems",
        icon="mdi:alert-decagram",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_problems,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CheckmkConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Checkmk sensors and keep them in sync with discovery."""
    coordinator = entry.runtime_data
    create_metrics = entry.options.get(
        CONF_CREATE_METRIC_SENSORS, DEFAULT_CREATE_METRIC_SENSORS
    )

    async_add_entities(
        CheckmkSummarySensor(coordinator, entry, description)
        for description in SUMMARY_SENSORS
    )

    known_hosts: set[str] = set()
    known_services: set[tuple[str, str]] = set()
    known_metrics: set[tuple[str, str, str]] = set()

    @callback
    def _discover() -> None:
        """Add entities for hosts/services/metrics that appeared in Checkmk."""
        data = coordinator.data or {"hosts": {}, "services": {}}
        new_entities: list[SensorEntity] = []

        # Ensure every host referenced by a service has a host sensor, even if
        # Checkmk reported the service before the host (or the host endpoint
        # filtered it out). This guarantees ``via_device`` always resolves.
        host_names = set(data["hosts"]) | {
            host for host, _ in data["services"]
        }

        for host in host_names:
            if host not in known_hosts:
                known_hosts.add(host)
                new_entities.append(CheckmkHostSensor(coordinator, entry, host))

        for key, service in data["services"].items():
            if key not in known_services:
                known_services.add(key)
                new_entities.append(CheckmkServiceSensor(coordinator, entry, key))

            if create_metrics:
                for metric in parse_perf_data(service.get("perf_data")):
                    metric_key = (*key, metric)
                    if metric_key not in known_metrics:
                        known_metrics.add(metric_key)
                        new_entities.append(
                            CheckmkMetricSensor(coordinator, entry, key, metric)
                        )

        if new_entities:
            async_add_entities(new_entities)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))


class CheckmkBaseEntity(CoordinatorEntity[CheckmkCoordinator]):
    """Common base for all Checkmk entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: CheckmkCoordinator, entry: CheckmkConfigEntry) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._entry = entry

    @property
    def _hub_device(self) -> DeviceInfo:
        """Return the device info for the Checkmk site itself."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"Checkmk ({self._entry.title})",
            manufacturer="Checkmk",
            entry_type="service",
            configuration_url=self._entry.data.get(CONF_URL),
        )

    def _host_device(self, host: str) -> DeviceInfo:
        """Return the device info for a monitored host."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{host}")},
            name=host,
            manufacturer="Checkmk",
            model="Monitored host",
            via_device=(DOMAIN, self._entry.entry_id),
        )


class CheckmkSummarySensor(CheckmkBaseEntity, SensorEntity):
    """A site-wide summary sensor (counts of hosts/services/problems)."""

    entity_description: CheckmkSummaryDescription

    def __init__(
        self,
        coordinator: CheckmkCoordinator,
        entry: CheckmkConfigEntry,
        description: CheckmkSummaryDescription,
    ) -> None:
        """Initialise the summary sensor."""
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = self._hub_device

    @property
    def native_value(self) -> int | None:
        """Return the computed summary value."""
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class CheckmkHostSensor(CheckmkBaseEntity, SensorEntity):
    """Reports the monitoring state of a single host."""

    _attr_name = "Status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(HOST_STATE.values())
    _attr_icon = "mdi:server"

    def __init__(
        self, coordinator: CheckmkCoordinator, entry: CheckmkConfigEntry, host: str
    ) -> None:
        """Initialise the host sensor."""
        super().__init__(coordinator, entry)
        self._host = host
        self._attr_unique_id = f"{entry.entry_id}_host_{host}"
        self._attr_device_info = self._host_device(host)

    @property
    def _data(self) -> dict[str, Any] | None:
        """Return the raw Checkmk record for this host."""
        return (self.coordinator.data or {}).get("hosts", {}).get(self._host)

    @property
    def available(self) -> bool:
        """Return whether the host is still known to Checkmk."""
        return super().available and self._data is not None

    @property
    def native_value(self) -> str | None:
        """Return the host state as a readable string."""
        if not (data := self._data):
            return None
        return HOST_STATE.get(data.get("state"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra detail about the host."""
        data = self._data or {}
        return _common_attributes(data) | {"address": data.get("address")}


class CheckmkServiceSensor(CheckmkBaseEntity, SensorEntity):
    """Reports the monitoring state of a single service."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(SERVICE_STATE.values())
    _attr_icon = "mdi:cog"

    def __init__(
        self,
        coordinator: CheckmkCoordinator,
        entry: CheckmkConfigEntry,
        key: tuple[str, str],
    ) -> None:
        """Initialise the service sensor."""
        super().__init__(coordinator, entry)
        self._key = key
        host, description = key
        self._host = host
        self._attr_name = description
        self._attr_unique_id = (
            f"{entry.entry_id}_service_{slugify(host)}_{slugify(description)}"
        )
        self._attr_device_info = self._host_device(host)

    @property
    def _data(self) -> dict[str, Any] | None:
        """Return the raw Checkmk record for this service."""
        return (self.coordinator.data or {}).get("services", {}).get(self._key)

    @property
    def available(self) -> bool:
        """Return whether the service is still known to Checkmk."""
        return super().available and self._data is not None

    @property
    def native_value(self) -> str | None:
        """Return the service state as a readable string."""
        if not (data := self._data):
            return None
        return SERVICE_STATE.get(data.get("state"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra detail about the service."""
        return _common_attributes(self._data or {})


class CheckmkMetricSensor(CheckmkBaseEntity, SensorEntity):
    """Reports a single numeric performance metric of a service."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: CheckmkCoordinator,
        entry: CheckmkConfigEntry,
        key: tuple[str, str],
        metric: str,
    ) -> None:
        """Initialise the metric sensor."""
        super().__init__(coordinator, entry)
        self._key = key
        self._metric = metric
        host, description = key
        self._attr_name = f"{description} {metric}"
        self._attr_unique_id = (
            f"{entry.entry_id}_metric_{slugify(host)}_"
            f"{slugify(description)}_{slugify(metric)}"
        )
        self._attr_device_info = self._host_device(host)

    @property
    def _parsed(self) -> tuple[float, str | None] | None:
        """Return the parsed ``(value, unit)`` for this metric."""
        service = (self.coordinator.data or {}).get("services", {}).get(self._key)
        if not service:
            return None
        return parse_perf_data(service.get("perf_data")).get(self._metric)

    @property
    def available(self) -> bool:
        """Return whether the metric is still present."""
        return super().available and self._parsed is not None

    @property
    def native_value(self) -> float | None:
        """Return the numeric metric value."""
        parsed = self._parsed
        return parsed[0] if parsed else None

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit reported by Checkmk, mapped where possible."""
        parsed = self._parsed
        if not parsed or not parsed[1]:
            return None
        return _UNIT_MAP.get(parsed[1], parsed[1])


def _common_attributes(data: dict[str, Any]) -> dict[str, Any]:
    """Return state attributes shared by host and service sensors."""
    last_check = data.get("last_check")
    return {
        "plugin_output": data.get("plugin_output"),
        "acknowledged": bool(data.get("acknowledged")),
        "in_downtime": bool(data.get("scheduled_downtime_depth")),
        "last_check": (
            dt_util.utc_from_timestamp(last_check).isoformat()
            if last_check
            else None
        ),
    }
