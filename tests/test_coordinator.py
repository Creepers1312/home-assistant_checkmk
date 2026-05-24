"""Tests for the Checkmk data update coordinator's filter logic."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.checkmk.const import DOMAIN
from custom_components.checkmk.coordinator import CheckmkCoordinator

ENTRY_DATA = {
    CONF_URL: "https://cmk.example.com/mysite",
    CONF_USERNAME: "auto",
    CONF_PASSWORD: "secret",
    CONF_VERIFY_SSL: True,
}


def _make_hosts() -> list[dict]:
    return [
        {"name": "web-01", "state": 0},
        {"name": "web-02", "state": 1},
        {"name": "db-01", "state": 0},
        {"name": "infra-01", "state": 0},
    ]


def _make_services() -> list[dict]:
    return [
        {"host_name": "web-01", "description": "CPU load", "state": 0},
        {"host_name": "web-01", "description": "NTP Time", "state": 1},
        {"host_name": "db-01", "description": "CPU load", "state": 0},
        {"host_name": "infra-01", "description": "CPU load", "state": 0},
        # Orphan: belongs to a host the host endpoint did not return.
        {"host_name": "ghost", "description": "CPU load", "state": 0},
    ]


def _build_coordinator(
    hass: HomeAssistant,
    **filters,
) -> CheckmkCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA, options={})
    entry.add_to_hass(hass)
    client = AsyncMock()
    client.async_get_hosts = AsyncMock(return_value=_make_hosts())
    client.async_get_services = AsyncMock(return_value=_make_services())
    return CheckmkCoordinator(hass, entry, client, scan_interval=60, **filters)


class TestCoordinatorFilters:
    async def test_unfiltered_returns_everything(self, hass: HomeAssistant) -> None:
        coordinator = _build_coordinator(hass)
        data = await coordinator._async_update_data()
        assert set(data["hosts"]) == {"web-01", "web-02", "db-01", "infra-01"}
        # The orphan service is still kept - it just won't pass any host filter.
        assert ("ghost", "CPU load") in data["services"]

    async def test_host_include_keeps_only_matches(
        self, hass: HomeAssistant
    ) -> None:
        coordinator = _build_coordinator(hass, host_include=["web-*"])
        data = await coordinator._async_update_data()
        assert set(data["hosts"]) == {"web-01", "web-02"}
        # Services on excluded hosts are dropped too - otherwise they would
        # try to attach to a non-existent host device.
        assert all(host.startswith("web-") for host, _ in data["services"])

    async def test_host_exclude_overrides_include(
        self, hass: HomeAssistant
    ) -> None:
        coordinator = _build_coordinator(
            hass, host_include=["*"], host_exclude=["infra-*"]
        )
        data = await coordinator._async_update_data()
        assert "infra-01" not in data["hosts"]
        assert ("infra-01", "CPU load") not in data["services"]

    async def test_service_exclude_drops_matching_descriptions(
        self, hass: HomeAssistant
    ) -> None:
        coordinator = _build_coordinator(hass, service_exclude=["NTP*"])
        data = await coordinator._async_update_data()
        # All hosts remain, only the NTP service is gone.
        assert "web-01" in data["hosts"]
        assert ("web-01", "NTP Time") not in data["services"]
        assert ("web-01", "CPU load") in data["services"]

    async def test_service_include_keeps_only_matches(
        self, hass: HomeAssistant
    ) -> None:
        coordinator = _build_coordinator(hass, service_include=["CPU *"])
        data = await coordinator._async_update_data()
        descriptions = {desc for _, desc in data["services"]}
        assert descriptions == {"CPU load"}
