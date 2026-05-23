"""Tests for the Checkmk REST API client."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.checkmk.api import (
    CheckmkApiError,
    CheckmkAuthError,
    CheckmkClient,
    CheckmkConnectionError,
)


def _fake_session(status: int, payload: Any = "") -> MagicMock:
    """Return a MagicMock that behaves like an aiohttp ClientSession."""
    response = MagicMock()
    response.status = status
    if isinstance(payload, (dict, list)):
        response.json = AsyncMock(return_value=payload)
        response.text = AsyncMock(return_value=json.dumps(payload))
    elif payload == "" and status == 204:
        response.json = AsyncMock(side_effect=ValueError("empty"))
        response.text = AsyncMock(return_value="")
    else:
        response.json = AsyncMock(side_effect=ValueError("not json"))
        response.text = AsyncMock(return_value=str(payload))

    session = MagicMock()
    session.request = AsyncMock(return_value=response)
    return session


def _client(session: MagicMock) -> CheckmkClient:
    return CheckmkClient(
        session, "https://cmk.example.com/mysite", "auto", "secret"
    )


class TestRequestErrors:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [401, 403])
    async def test_auth_failures_raise_auth_error(self, status: int) -> None:
        client = _client(_fake_session(status, "denied"))
        with pytest.raises(CheckmkAuthError):
            await client.async_validate()

    @pytest.mark.asyncio
    async def test_404_is_treated_as_connection_error(self) -> None:
        # The site URL was probably wrong - this needs to map to
        # "cannot_connect" so the config flow can surface a useful error.
        client = _client(_fake_session(404, "not found"))
        with pytest.raises(CheckmkConnectionError):
            await client.async_validate()

    @pytest.mark.asyncio
    async def test_500_raises_generic_api_error(self) -> None:
        client = _client(_fake_session(500, "boom"))
        with pytest.raises(CheckmkApiError):
            await client.async_validate()

    @pytest.mark.asyncio
    async def test_invalid_json_raises_api_error(self) -> None:
        client = _client(_fake_session(200, "not actually json"))
        with pytest.raises(CheckmkApiError):
            await client.async_validate()


class TestAuthHeader:
    @pytest.mark.asyncio
    async def test_auth_header_uses_bearer_format(self) -> None:
        session = _fake_session(200, {"versions": {"checkmk": "2.3.0"}})
        client = _client(session)
        await client.async_validate()

        _, kwargs = session.request.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer auto secret"
        assert kwargs["headers"]["Accept"] == "application/json"


class TestGetHosts:
    @pytest.mark.asyncio
    async def test_returns_flat_extensions_list(self) -> None:
        payload = {
            "value": [
                {"extensions": {"name": "db01", "state": 0}},
                {"extensions": {"name": "db02", "state": 2}},
            ]
        }
        session = _fake_session(200, payload)
        client = _client(session)

        hosts = await client.async_get_hosts()
        assert hosts == [
            {"name": "db01", "state": 0},
            {"name": "db02", "state": 2},
        ]

    @pytest.mark.asyncio
    async def test_requests_expected_columns(self) -> None:
        session = _fake_session(200, {"value": []})
        client = _client(session)
        await client.async_get_hosts()

        _, kwargs = session.request.call_args
        column_values = [value for key, value in kwargs["params"] if key == "columns"]
        # The exact column set is part of the contract with Checkmk - missing
        # columns would silently turn into empty sensor attributes.
        for required in ("name", "state", "last_check", "plugin_output", "address"):
            assert required in column_values


class TestGetServices:
    @pytest.mark.asyncio
    async def test_returns_flat_extensions_list(self) -> None:
        payload = {
            "value": [
                {
                    "extensions": {
                        "host_name": "db01",
                        "description": "CPU load",
                        "state": 1,
                    }
                }
            ]
        }
        session = _fake_session(200, payload)
        client = _client(session)

        services = await client.async_get_services()
        assert services == [
            {"host_name": "db01", "description": "CPU load", "state": 1}
        ]


class TestPostActions:
    @pytest.mark.asyncio
    async def test_acknowledge_host_posts_expected_body(self) -> None:
        session = _fake_session(204)
        client = _client(session)

        await client.async_acknowledge_host(
            "db01", comment="rebuilding index"
        )

        method, kwargs = session.request.call_args.args[0], session.request.call_args.kwargs
        assert method == "POST"
        assert kwargs["json"] == {
            "acknowledge_type": "host",
            "host_name": "db01",
            "comment": "rebuilding index",
            "sticky": True,
            "notify": True,
            "persistent": False,
        }
        assert kwargs["headers"]["Content-Type"] == "application/json"

    @pytest.mark.asyncio
    async def test_acknowledge_service_includes_description(self) -> None:
        session = _fake_session(204)
        client = _client(session)

        await client.async_acknowledge_service(
            "db01", "CPU load", comment="known"
        )
        body = session.request.call_args.kwargs["json"]
        assert body["service_description"] == "CPU load"
        assert body["acknowledge_type"] == "service"

    @pytest.mark.asyncio
    async def test_schedule_service_downtime_serialises_iterable(self) -> None:
        session = _fake_session(204)
        client = _client(session)

        # Passing a tuple/generator must still produce a JSON array.
        await client.async_schedule_service_downtime(
            "db01",
            (s for s in ["CPU load", "Memory"]),
            start_time="2026-01-01T00:00:00+00:00",
            end_time="2026-01-01T01:00:00+00:00",
            comment="maintenance",
        )
        body = session.request.call_args.kwargs["json"]
        assert body["service_descriptions"] == ["CPU load", "Memory"]

