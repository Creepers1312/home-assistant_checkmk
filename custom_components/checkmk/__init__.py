"""The Checkmk integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CheckmkClient
from .const import (
    CONF_HOST_EXCLUDE,
    CONF_HOST_INCLUDE,
    CONF_SERVICE_EXCLUDE,
    CONF_SERVICE_INCLUDE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
)
from .coordinator import CheckmkCoordinator
from .parsing import extract_macs, parse_pattern_list
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
    coordinator = CheckmkCoordinator(
        hass,
        entry,
        client,
        scan_interval,
        host_include=parse_pattern_list(entry.options.get(CONF_HOST_INCLUDE)),
        host_exclude=parse_pattern_list(entry.options.get(CONF_HOST_EXCLUDE)),
        service_include=parse_pattern_list(
            entry.options.get(CONF_SERVICE_INCLUDE)
        ),
        service_exclude=parse_pattern_list(
            entry.options.get(CONF_SERVICE_EXCLUDE)
        ),
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    _async_register_devices(hass, entry, coordinator.data)

    @callback
    def _sync_devices() -> None:
        _async_register_devices(hass, entry, coordinator.data)

    entry.async_on_unload(coordinator.async_add_listener(_sync_devices))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    async_register_services(hass)
    return True


@callback
def _async_register_devices(
    hass: HomeAssistant,
    entry: CheckmkConfigEntry,
    data: dict[str, Any] | None,
) -> None:
    """Register the hub + host devices with their MAC connections.

    Running this on every coordinator update keeps device entries in sync
    with the MACs we can pull out of interface plugin outputs. The lookups
    are in-memory and idempotent, so re-running is cheap.
    """
    device_registry = dr.async_get(hass)

    # Hub device upfront so per-host devices always have a resolvable parent
    # even if a platform hasn't registered yet.
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Checkmk ({entry.title})",
        manufacturer="Checkmk",
        entry_type=dr.DeviceEntryType.SERVICE,
        configuration_url=entry.data.get(CONF_URL),
    )

    if not data:
        return

    services_by_host: dict[str, list[dict[str, Any]]] = {}
    for (host, _desc), service in data.get("services", {}).items():
        services_by_host.setdefault(host, []).append(service)

    host_names = set(data.get("hosts", {})) | set(services_by_host)
    for host in host_names:
        macs = extract_macs(services_by_host.get(host, []))
        if not macs:
            continue
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{entry.entry_id}_{host}")},
            connections={(dr.CONNECTION_NETWORK_MAC, mac) for mac in macs},
            name=host,
            manufacturer="Checkmk",
            model="Monitored host",
            via_device=(DOMAIN, entry.entry_id),
        )


async def async_unload_entry(hass: HomeAssistant, entry: CheckmkConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: CheckmkConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
