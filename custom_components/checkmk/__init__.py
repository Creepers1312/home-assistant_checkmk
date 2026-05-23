"""The Checkmk integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CheckmkClient
from .const import DEFAULT_SCAN_INTERVAL, DEFAULT_VERIFY_SSL
from .coordinator import CheckmkCoordinator
from .services import async_register_services

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

type CheckmkConfigEntry = ConfigEntry[CheckmkCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: CheckmkConfigEntry) -> bool:
    """Set up Checkmk from a config entry."""
    verify_ssl = entry.data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    session = async_get_clientsession(hass, verify_ssl=verify_ssl)

    client = CheckmkClient(
        session,
        entry.data[CONF_URL],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = CheckmkCoordinator(hass, entry, client, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CheckmkConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: CheckmkConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
