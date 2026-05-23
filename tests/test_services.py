"""Tests for the Checkmk integration services."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.checkmk.api import CheckmkApiError
from custom_components.checkmk.const import DOMAIN

ENTRY_DATA = {
    CONF_URL: "https://cmk.example.com/mysite",
    CONF_USERNAME: "auto",
    CONF_PASSWORD: "secret",
    CONF_VERIFY_SSL: True,
}


@pytest.fixture
def mock_client() -> MagicMock:
    """Return a ``CheckmkClient`` substitute with every method mocked."""
    client = MagicMock()
    client.async_validate = AsyncMock(return_value={})
    client.async_get_hosts = AsyncMock(return_value=[])
    client.async_get_services = AsyncMock(return_value=[])
    client.async_acknowledge_host = AsyncMock()
    client.async_acknowledge_service = AsyncMock()
    client.async_schedule_host_downtime = AsyncMock()
    client.async_schedule_service_downtime = AsyncMock()
    client.async_reschedule_host_check = AsyncMock()
    client.async_reschedule_service_check = AsyncMock()
    return client


@pytest.fixture
async def loaded_entry(
    hass: HomeAssistant, mock_client: MagicMock
) -> MockConfigEntry:
    """Set up a Checkmk config entry whose client is the mock."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=ENTRY_DATA[CONF_URL].lower(),
        data=ENTRY_DATA,
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.checkmk.CheckmkClient", return_value=mock_client
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


class TestAcknowledge:
    async def test_host_acknowledge_calls_host_endpoint(
        self,
        hass: HomeAssistant,
        loaded_entry: MockConfigEntry,
        mock_client: MagicMock,
    ) -> None:
        await hass.services.async_call(
            DOMAIN,
            "acknowledge",
            {"host": "db01", "comment": "investigating"},
            blocking=True,
        )
        mock_client.async_acknowledge_host.assert_awaited_once_with(
            "db01",
            comment="investigating",
            sticky=True,
            notify=True,
            persistent=False,
        )
        mock_client.async_acknowledge_service.assert_not_awaited()

    async def test_service_acknowledge_calls_service_endpoint(
        self,
        hass: HomeAssistant,
        loaded_entry: MockConfigEntry,
        mock_client: MagicMock,
    ) -> None:
        await hass.services.async_call(
            DOMAIN,
            "acknowledge",
            {
                "host": "db01",
                "service": "CPU load",
                "comment": "known",
                "sticky": False,
            },
            blocking=True,
        )
        mock_client.async_acknowledge_service.assert_awaited_once_with(
            "db01",
            "CPU load",
            comment="known",
            sticky=False,
            notify=True,
            persistent=False,
        )
        mock_client.async_acknowledge_host.assert_not_awaited()

    async def test_api_failure_is_raised_as_home_assistant_error(
        self,
        hass: HomeAssistant,
        loaded_entry: MockConfigEntry,
        mock_client: MagicMock,
    ) -> None:
        mock_client.async_acknowledge_host.side_effect = CheckmkApiError(
            "Checkmk said no"
        )
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                DOMAIN,
                "acknowledge",
                {"host": "db01", "comment": "x"},
                blocking=True,
            )


class TestScheduleDowntime:
    async def test_host_downtime_with_duration_default(
        self,
        hass: HomeAssistant,
        loaded_entry: MockConfigEntry,
        mock_client: MagicMock,
    ) -> None:
        await hass.services.async_call(
            DOMAIN,
            "schedule_downtime",
            {"host": "db01", "comment": "patch"},
            blocking=True,
        )
        mock_client.async_schedule_host_downtime.assert_awaited_once()
        kwargs = mock_client.async_schedule_host_downtime.await_args.kwargs
        # No duration was passed - default is 60 minutes, so end_time should be
        # exactly an hour after start_time (within a few seconds of "now").
        start = datetime.fromisoformat(kwargs["start_time"])
        end = datetime.fromisoformat(kwargs["end_time"])
        assert (end - start).total_seconds() == 3600
        assert kwargs["comment"] == "patch"

    async def test_service_downtime_with_explicit_window(
        self,
        hass: HomeAssistant,
        loaded_entry: MockConfigEntry,
        mock_client: MagicMock,
    ) -> None:
        start = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        end = datetime(2026, 1, 1, 11, 30, tzinfo=timezone.utc)
        await hass.services.async_call(
            DOMAIN,
            "schedule_downtime",
            {
                "host": "db01",
                "services": ["CPU load", "Memory"],
                "comment": "maintenance",
                "start_time": start.isoformat(),
                "end_time": end.isoformat(),
            },
            blocking=True,
        )
        call = mock_client.async_schedule_service_downtime.await_args
        assert call.args[0] == "db01"
        assert call.args[1] == ["CPU load", "Memory"]
        assert call.kwargs["start_time"] == start.isoformat()
        assert call.kwargs["end_time"] == end.isoformat()

    async def test_duration_and_end_time_are_mutually_exclusive(
        self,
        hass: HomeAssistant,
        loaded_entry: MockConfigEntry,
    ) -> None:
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "schedule_downtime",
                {
                    "host": "db01",
                    "comment": "x",
                    "duration": 30,
                    "end_time": "2026-01-01T11:00:00+00:00",
                },
                blocking=True,
            )

    async def test_end_before_start_is_rejected(
        self,
        hass: HomeAssistant,
        loaded_entry: MockConfigEntry,
    ) -> None:
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "schedule_downtime",
                {
                    "host": "db01",
                    "comment": "x",
                    "start_time": "2026-01-01T12:00:00+00:00",
                    "end_time": "2026-01-01T11:00:00+00:00",
                },
                blocking=True,
            )


class TestRescheduleCheck:
    async def test_host_recheck(
        self,
        hass: HomeAssistant,
        loaded_entry: MockConfigEntry,
        mock_client: MagicMock,
    ) -> None:
        await hass.services.async_call(
            DOMAIN, "reschedule_check", {"host": "db01"}, blocking=True
        )
        mock_client.async_reschedule_host_check.assert_awaited_once_with("db01")

    async def test_service_recheck(
        self,
        hass: HomeAssistant,
        loaded_entry: MockConfigEntry,
        mock_client: MagicMock,
    ) -> None:
        await hass.services.async_call(
            DOMAIN,
            "reschedule_check",
            {"host": "db01", "service": "CPU load"},
            blocking=True,
        )
        mock_client.async_reschedule_service_check.assert_awaited_once_with(
            "db01", "CPU load"
        )


class TestConfigEntryResolution:
    async def test_unknown_config_entry_id_raises(
        self,
        hass: HomeAssistant,
        loaded_entry: MockConfigEntry,
    ) -> None:
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN,
                "reschedule_check",
                {"host": "db01", "config_entry_id": "doesnotexist"},
                blocking=True,
            )

    async def test_multiple_entries_require_explicit_id(
        self,
        hass: HomeAssistant,
        mock_client: MagicMock,
        loaded_entry: MockConfigEntry,
    ) -> None:
        second = MockConfigEntry(
            domain=DOMAIN,
            unique_id="https://other.example.com/site",
            data={**ENTRY_DATA, CONF_URL: "https://other.example.com/site"},
        )
        second.add_to_hass(hass)
        with patch(
            "custom_components.checkmk.CheckmkClient", return_value=mock_client
        ):
            assert await hass.config_entries.async_setup(second.entry_id)
            await hass.async_block_till_done()

        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN, "reschedule_check", {"host": "db01"}, blocking=True
            )

        # ... but works when the caller picks one explicitly.
        await hass.services.async_call(
            DOMAIN,
            "reschedule_check",
            {"host": "db01", "config_entry_id": loaded_entry.entry_id},
            blocking=True,
        )
        mock_client.async_reschedule_host_check.assert_awaited_with("db01")
