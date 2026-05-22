"""Lightweight async client for the Checkmk REST API (Checkmk 2.1+)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import ClientError, ClientSession

_LOGGER = logging.getLogger(__name__)

API_PATH = "check_mk/api/1.0"
TIMEOUT = 30

# Livestatus columns requested for monitored hosts.
HOST_COLUMNS = (
    "name",
    "state",
    "last_check",
    "plugin_output",
    "acknowledged",
    "scheduled_downtime_depth",
    "address",
)

# Livestatus columns requested for monitored services.
SERVICE_COLUMNS = (
    "host_name",
    "description",
    "state",
    "last_check",
    "plugin_output",
    "acknowledged",
    "scheduled_downtime_depth",
    "perf_data",
)


class CheckmkApiError(Exception):
    """Raised for a generic Checkmk API failure."""


class CheckmkAuthError(CheckmkApiError):
    """Raised when authentication against Checkmk fails."""


class CheckmkConnectionError(CheckmkApiError):
    """Raised when Checkmk cannot be reached."""


class CheckmkClient:
    """Minimal async wrapper around the Checkmk monitoring REST API."""

    def __init__(
        self,
        session: ClientSession,
        url: str,
        username: str,
        secret: str,
    ) -> None:
        """Initialise the client.

        ``url`` is the base URL of the Checkmk *site*, e.g.
        ``https://monitoring.example.com/mysite``.
        """
        self._session = session
        self._base = f"{url.rstrip('/')}/{API_PATH}"
        self._username = username
        self._secret = secret

    @property
    def _headers(self) -> dict[str, str]:
        """Return the Checkmk automation auth headers."""
        return {
            "Authorization": f"Bearer {self._username} {self._secret}",
            "Accept": "application/json",
        }

    async def _get(
        self, endpoint: str, params: list[tuple[str, str]] | None = None
    ) -> dict[str, Any]:
        """Perform an authenticated GET request and return the JSON body."""
        url = f"{self._base}/{endpoint}"
        try:
            async with asyncio.timeout(TIMEOUT):
                response = await self._session.get(
                    url, headers=self._headers, params=params
                )
        except asyncio.TimeoutError as err:
            raise CheckmkConnectionError(f"Timeout connecting to {url}") from err
        except ClientError as err:
            raise CheckmkConnectionError(f"Cannot connect to {url}: {err}") from err

        if response.status in (401, 403):
            raise CheckmkAuthError("Invalid Checkmk credentials")
        if response.status >= 400:
            body = await response.text()
            raise CheckmkApiError(
                f"Checkmk API returned HTTP {response.status}: {body[:200]}"
            )

        try:
            return await response.json()
        except (ValueError, ClientError) as err:
            raise CheckmkApiError(f"Invalid JSON response from {url}") from err

    async def async_validate(self) -> dict[str, Any]:
        """Validate the connection and credentials; return the version info."""
        return await self._get("version")

    async def async_get_hosts(self) -> list[dict[str, Any]]:
        """Return the monitoring state of all hosts."""
        params = [("columns", column) for column in HOST_COLUMNS]
        data = await self._get("domain-types/host/collections/all", params)
        return [item.get("extensions", {}) for item in data.get("value", [])]

    async def async_get_services(self) -> list[dict[str, Any]]:
        """Return the monitoring state of all services."""
        params = [("columns", column) for column in SERVICE_COLUMNS]
        data = await self._get("domain-types/service/collections/all", params)
        return [item.get("extensions", {}) for item in data.get("value", [])]
