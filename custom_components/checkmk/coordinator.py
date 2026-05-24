"""Data update coordinator for the Checkmk integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CheckmkApiError, CheckmkAuthError, CheckmkClient
from .parsing import matches_filter

_LOGGER = logging.getLogger(__name__)

type CheckmkData = dict[str, dict[Any, dict[str, Any]]]


class CheckmkCoordinator(DataUpdateCoordinator[CheckmkData]):
    """Polls the Checkmk REST API and caches host/service state."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: CheckmkClient,
        scan_interval: int,
        *,
        host_include: list[str] | None = None,
        host_exclude: list[str] | None = None,
        service_include: list[str] | None = None,
        service_exclude: list[str] | None = None,
    ) -> None:
        """Initialise the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Checkmk",
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._host_include = host_include or []
        self._host_exclude = host_exclude or []
        self._service_include = service_include or []
        self._service_exclude = service_exclude or []

    def _host_passes(self, host: str) -> bool:
        return matches_filter(host, self._host_include, self._host_exclude)

    def _service_passes(self, host: str, description: str) -> bool:
        # A service is only kept when its host also passes - otherwise the
        # service would show up under a non-existent host device.
        if not self._host_passes(host):
            return False
        return matches_filter(
            description, self._service_include, self._service_exclude
        )

    async def _async_update_data(self) -> CheckmkData:
        """Fetch the current host and service state from Checkmk."""
        try:
            hosts, services = await asyncio.gather(
                self.client.async_get_hosts(),
                self.client.async_get_services(),
            )
        except CheckmkAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except CheckmkApiError as err:
            raise UpdateFailed(str(err)) from err

        return {
            "hosts": {
                host["name"]: host
                for host in hosts
                if host.get("name") and self._host_passes(host["name"])
            },
            "services": {
                (service["host_name"], service["description"]): service
                for service in services
                if service.get("host_name")
                and service.get("description")
                and self._service_passes(
                    service["host_name"], service["description"]
                )
            },
        }
