"""Lightweight async client for the Checkmk REST API (Checkmk 2.1+)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable

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

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: list[tuple[str, str]] | None = None,
        json: dict[str, Any] | None = None,
        expect_json: bool = True,
    ) -> dict[str, Any]:
        """Perform an authenticated request and return the JSON body."""
        url = f"{self._base}/{endpoint}"
        headers = self._headers
        if json is not None:
            headers = {**headers, "Content-Type": "application/json"}
        try:
            async with asyncio.timeout(TIMEOUT):
                response = await self._session.request(
                    method, url, headers=headers, params=params, json=json
                )
        except asyncio.TimeoutError as err:
            raise CheckmkConnectionError(f"Timeout connecting to {url}") from err
        except ClientError as err:
            raise CheckmkConnectionError(f"Cannot connect to {url}: {err}") from err

        if response.status in (401, 403):
            raise CheckmkAuthError("Invalid Checkmk credentials")
        # 404 on the API root usually means the site URL is wrong (missing site
        # name, wrong protocol, etc.) - surface that as a connection problem so
        # the config flow shows a useful error instead of a generic "unknown".
        if response.status == 404:
            raise CheckmkConnectionError(
                f"Checkmk API not found at {url} (HTTP 404); "
                "check the site URL"
            )
        if response.status >= 400:
            body = await response.text()
            raise CheckmkApiError(
                f"Checkmk API returned HTTP {response.status}: {body[:200]}"
            )

        if not expect_json or response.status == 204:
            return {}
        try:
            return await response.json()
        except (ValueError, ClientError) as err:
            raise CheckmkApiError(f"Invalid JSON response from {url}") from err

    async def _get(
        self, endpoint: str, params: list[tuple[str, str]] | None = None
    ) -> dict[str, Any]:
        """Perform an authenticated GET request."""
        return await self._request("GET", endpoint, params=params)

    async def _post(
        self,
        endpoint: str,
        json: dict[str, Any] | None = None,
        *,
        expect_json: bool = False,
    ) -> dict[str, Any]:
        """Perform an authenticated POST request."""
        return await self._request(
            "POST", endpoint, json=json, expect_json=expect_json
        )

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

    async def async_acknowledge_host(
        self,
        host: str,
        *,
        comment: str,
        sticky: bool = True,
        notify: bool = True,
        persistent: bool = False,
    ) -> None:
        """Acknowledge problems on a host."""
        await self._post(
            "domain-types/acknowledge/collections/host",
            {
                "acknowledge_type": "host",
                "host_name": host,
                "comment": comment,
                "sticky": sticky,
                "notify": notify,
                "persistent": persistent,
            },
        )

    async def async_acknowledge_service(
        self,
        host: str,
        service: str,
        *,
        comment: str,
        sticky: bool = True,
        notify: bool = True,
        persistent: bool = False,
    ) -> None:
        """Acknowledge problems on a service."""
        await self._post(
            "domain-types/acknowledge/collections/service",
            {
                "acknowledge_type": "service",
                "host_name": host,
                "service_description": service,
                "comment": comment,
                "sticky": sticky,
                "notify": notify,
                "persistent": persistent,
            },
        )

    async def async_schedule_host_downtime(
        self,
        host: str,
        *,
        start_time: str,
        end_time: str,
        comment: str,
    ) -> None:
        """Schedule a fixed downtime for a host."""
        await self._post(
            "domain-types/downtime/collections/host",
            {
                "downtime_type": "host",
                "host_name": host,
                "start_time": start_time,
                "end_time": end_time,
                "comment": comment,
            },
        )

    async def async_schedule_service_downtime(
        self,
        host: str,
        services: Iterable[str],
        *,
        start_time: str,
        end_time: str,
        comment: str,
    ) -> None:
        """Schedule a fixed downtime for one or more services on a host."""
        await self._post(
            "domain-types/downtime/collections/service",
            {
                "downtime_type": "service",
                "host_name": host,
                "service_descriptions": list(services),
                "start_time": start_time,
                "end_time": end_time,
                "comment": comment,
            },
        )

    async def async_reschedule_host_check(self, host: str) -> None:
        """Trigger an immediate host check."""
        await self._post(
            "domain-types/host/actions/reschedule_check/invoke",
            {"host_name": host},
        )

    async def async_reschedule_service_check(
        self, host: str, service: str
    ) -> None:
        """Trigger an immediate service check."""
        await self._post(
            "domain-types/service/actions/reschedule_check/invoke",
            {"host_name": host, "service_description": service},
        )
