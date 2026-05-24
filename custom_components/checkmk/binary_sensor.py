"""Binary sensor platform for the Checkmk integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import CheckmkConfigEntry
from .const import DOMAIN
from .coordinator import CheckmkCoordinator
from .parsing import is_problem


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CheckmkConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Checkmk binary sensors and keep them in sync with discovery."""
    coordinator = entry.runtime_data

    async_add_entities([CheckmkSiteProblemSensor(coordinator, entry)])

    known_hosts: set[str] = set()

    @callback
    def _discover() -> None:
        data = coordinator.data or {"hosts": {}, "services": {}}

        # Treat host names referenced by services as known so we always have a
        # host-level problem sensor even if Checkmk omitted the host record.
        host_names = set(data["hosts"]) | {h for h, _ in data["services"]}

        new_entities: list[BinarySensorEntity] = []
        for host in host_names:
            if host not in known_hosts:
                known_hosts.add(host)
                new_entities.append(CheckmkHostProblemSensor(coordinator, entry, host))

        if new_entities:
            async_add_entities(new_entities)

    _discover()
    entry.async_on_unload(coordinator.async_add_listener(_discover))


class _CheckmkBinaryBase(CoordinatorEntity[CheckmkCoordinator], BinarySensorEntity):
    """Common base for all Checkmk binary sensors."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self, coordinator: CheckmkCoordinator, entry: CheckmkConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry

    @property
    def _hub_device(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"Checkmk ({self._entry.title})",
            manufacturer="Checkmk",
            entry_type="service",
            configuration_url=self._entry.data.get(CONF_URL),
        )

    def _host_device(self, host: str) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{host}")},
            name=host,
            manufacturer="Checkmk",
            model="Monitored host",
            via_device=(DOMAIN, self._entry.entry_id),
        )


class CheckmkSiteProblemSensor(_CheckmkBinaryBase):
    """On if the Checkmk site reports at least one unhandled problem."""

    _attr_name = "Problems"
    _attr_icon = "mdi:alert-decagram"

    def __init__(
        self, coordinator: CheckmkCoordinator, entry: CheckmkConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_has_problems"
        self._attr_device_info = self._hub_device

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not data:
            return None
        return any(
            is_problem(entry)
            for entry in (*data["hosts"].values(), *data["services"].values())
        )


class CheckmkHostProblemSensor(_CheckmkBinaryBase):
    """On while a single monitored host is in an unhandled problem state."""

    _attr_name = "Problem"

    def __init__(
        self,
        coordinator: CheckmkCoordinator,
        entry: CheckmkConfigEntry,
        host: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._host = host
        self._attr_unique_id = f"{entry.entry_id}_host_problem_{host}"
        self._attr_device_info = self._host_device(host)

    @property
    def _data(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("hosts", {}).get(self._host)

    @property
    def available(self) -> bool:
        return super().available and self._data is not None

    @property
    def is_on(self) -> bool | None:
        if not (data := self._data):
            return None
        return is_problem(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return _common_attributes(self._data or {})


def _common_attributes(data: dict[str, Any]) -> dict[str, Any]:
    """Return state attributes shared by host and service binary sensors."""
    last_check = data.get("last_check")
    return {
        "state": data.get("state"),
        "plugin_output": data.get("plugin_output"),
        "acknowledged": bool(data.get("acknowledged")),
        "in_downtime": bool(data.get("scheduled_downtime_depth")),
        "last_check": (
            dt_util.utc_from_timestamp(last_check).isoformat()
            if last_check
            else None
        ),
    }
