"""Service calls for the Checkmk integration."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import CheckmkApiError, CheckmkAuthError
from .const import DOMAIN
from .coordinator import CheckmkCoordinator

SERVICE_ACKNOWLEDGE = "acknowledge"
SERVICE_SCHEDULE_DOWNTIME = "schedule_downtime"

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_HOST = "host"
ATTR_SERVICE = "service"
ATTR_SERVICES = "services"
ATTR_COMMENT = "comment"
ATTR_STICKY = "sticky"
ATTR_NOTIFY = "notify"
ATTR_PERSISTENT = "persistent"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_DURATION = "duration"

ACKNOWLEDGE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_HOST): cv.string,
        vol.Optional(ATTR_SERVICE): cv.string,
        vol.Required(ATTR_COMMENT): cv.string,
        vol.Optional(ATTR_STICKY, default=True): cv.boolean,
        vol.Optional(ATTR_NOTIFY, default=True): cv.boolean,
        vol.Optional(ATTR_PERSISTENT, default=False): cv.boolean,
    }
)

DOWNTIME_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_HOST): cv.string,
        vol.Optional(ATTR_SERVICES): vol.All(cv.ensure_list, [cv.string]),
        vol.Required(ATTR_COMMENT): cv.string,
        vol.Optional(ATTR_START_TIME): cv.datetime,
        vol.Optional(ATTR_END_TIME): cv.datetime,
        vol.Optional(ATTR_DURATION): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=24 * 60 * 7)
        ),
    }
)

def _resolve_coordinator(
    hass: HomeAssistant, call: ServiceCall
) -> CheckmkCoordinator:
    """Pick the Checkmk coordinator for this service call.

    If ``config_entry_id`` is provided it is used directly. Otherwise the call
    is unambiguous only when exactly one Checkmk integration is loaded.
    """
    entry_id = call.data.get(ATTR_CONFIG_ENTRY_ID)
    if entry_id is not None:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            raise ServiceValidationError(
                f"Config entry {entry_id} is not a Checkmk integration"
            )
        if getattr(entry, "runtime_data", None) is None:
            raise ServiceValidationError(
                f"Checkmk entry {entry.title} is not loaded"
            )
        return entry.runtime_data

    loaded = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    ]
    if len(loaded) == 1:
        return loaded[0].runtime_data
    if not loaded:
        raise ServiceValidationError("No loaded Checkmk integration found")
    raise ServiceValidationError(
        "Multiple Checkmk integrations are configured; "
        f"specify '{ATTR_CONFIG_ENTRY_ID}'"
    )


def _format_time(value: datetime) -> str:
    """Format a datetime as RFC 3339 with offset, accepted by the Checkmk API."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _downtime_window(
    data: dict[str, Any]
) -> tuple[str, str]:
    """Resolve ``start_time``/``end_time``/``duration`` into a Checkmk window."""
    start = data.get(ATTR_START_TIME) or datetime.now(timezone.utc)
    end = data.get(ATTR_END_TIME)
    duration = data.get(ATTR_DURATION)

    if end is None and duration is None:
        duration = 60
    if end is not None and duration is not None:
        raise ServiceValidationError(
            f"Use either '{ATTR_END_TIME}' or '{ATTR_DURATION}', not both"
        )
    if end is None:
        end = start + timedelta(minutes=duration)
    if end <= start:
        raise ServiceValidationError("Downtime end time must be after start time")
    return _format_time(start), _format_time(end)


async def _wrap_api(func, *args, **kwargs) -> None:
    """Translate Checkmk API exceptions into HA service errors."""
    try:
        await func(*args, **kwargs)
    except CheckmkAuthError as err:
        raise HomeAssistantError(f"Checkmk rejected the request: {err}") from err
    except CheckmkApiError as err:
        raise HomeAssistantError(f"Checkmk request failed: {err}") from err


async def _async_acknowledge(hass: HomeAssistant, call: ServiceCall) -> None:
    coordinator = _resolve_coordinator(hass, call)
    host = call.data[ATTR_HOST]
    service = call.data.get(ATTR_SERVICE)
    common = {
        "comment": call.data[ATTR_COMMENT],
        "sticky": call.data[ATTR_STICKY],
        "notify": call.data[ATTR_NOTIFY],
        "persistent": call.data[ATTR_PERSISTENT],
    }
    if service:
        await _wrap_api(
            coordinator.client.async_acknowledge_service, host, service, **common
        )
    else:
        await _wrap_api(coordinator.client.async_acknowledge_host, host, **common)
    await coordinator.async_request_refresh()


async def _async_schedule_downtime(hass: HomeAssistant, call: ServiceCall) -> None:
    coordinator = _resolve_coordinator(hass, call)
    start_time, end_time = _downtime_window(call.data)
    host = call.data[ATTR_HOST]
    services = call.data.get(ATTR_SERVICES) or []
    comment = call.data[ATTR_COMMENT]

    if services:
        await _wrap_api(
            coordinator.client.async_schedule_service_downtime,
            host,
            services,
            start_time=start_time,
            end_time=end_time,
            comment=comment,
        )
    else:
        await _wrap_api(
            coordinator.client.async_schedule_host_downtime,
            host,
            start_time=start_time,
            end_time=end_time,
            comment=comment,
        )
    await coordinator.async_request_refresh()


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register the Checkmk integration services (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_ACKNOWLEDGE):
        return

    async def _ack(call: ServiceCall) -> None:
        await _async_acknowledge(hass, call)

    async def _downtime(call: ServiceCall) -> None:
        await _async_schedule_downtime(hass, call)

    hass.services.async_register(
        DOMAIN, SERVICE_ACKNOWLEDGE, _ack, schema=ACKNOWLEDGE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SCHEDULE_DOWNTIME, _downtime, schema=DOWNTIME_SCHEMA
    )


