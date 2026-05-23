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
                host["name"]: host for host in hosts if host.get("name")
            },
            "services": {
                (service["host_name"], service["description"]): service
                for service in services
                if service.get("host_name") and service.get("description")
            },
        }
