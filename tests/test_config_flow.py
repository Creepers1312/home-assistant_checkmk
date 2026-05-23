"""Config flow tests for the Checkmk integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.checkmk.api import (
    CheckmkAuthError,
    CheckmkConnectionError,
)
from custom_components.checkmk.const import DOMAIN

VALID_INPUT = {
    CONF_URL: "https://cmk.example.com/mysite",
    CONF_USERNAME: "auto",
    CONF_PASSWORD: "secret",
    CONF_VERIFY_SSL: True,
}


def _patch_validate(side_effect=None, return_value=None):
    """Patch ``CheckmkClient.async_validate`` for the duration of a test."""
    return patch(
        "custom_components.checkmk.config_flow.CheckmkClient.async_validate",
        new=AsyncMock(side_effect=side_effect, return_value=return_value),
    )


class TestUserFlow:
    async def test_happy_path_creates_entry(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {}

        with _patch_validate(return_value={}):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], VALID_INPUT
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == VALID_INPUT[CONF_URL]
        assert result["data"][CONF_URL] == VALID_INPUT[CONF_URL]
        assert result["data"][CONF_USERNAME] == "auto"
        assert result["data"][CONF_PASSWORD] == "secret"

    async def test_trailing_slash_is_stripped(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        with _patch_validate(return_value={}):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {**VALID_INPUT, CONF_URL: VALID_INPUT[CONF_URL] + "/"},
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        # The stored URL must not keep the trailing slash; otherwise the API
        # base URL would double up its own slash and break requests.
        assert result["data"][CONF_URL] == VALID_INPUT[CONF_URL]

    @pytest.mark.parametrize(
        ("side_effect", "expected"),
        [
            (CheckmkAuthError("bad creds"), "invalid_auth"),
            (CheckmkConnectionError("nope"), "cannot_connect"),
            (RuntimeError("boom"), "unknown"),
        ],
    )
    async def test_validation_errors_are_surfaced(
        self, hass: HomeAssistant, side_effect: Exception, expected: str
    ) -> None:
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        with _patch_validate(side_effect=side_effect):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], VALID_INPUT
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": expected}

    async def test_duplicate_site_is_aborted(self, hass: HomeAssistant) -> None:
        MockConfigEntry(
            domain=DOMAIN,
            unique_id=VALID_INPUT[CONF_URL].lower(),
            data=VALID_INPUT,
        ).add_to_hass(hass)

        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data=VALID_INPUT,
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"


class TestReauthFlow:
    async def test_reauth_updates_entry_on_success(
        self, hass: HomeAssistant
    ) -> None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id=VALID_INPUT[CONF_URL].lower(),
            data=VALID_INPUT,
        )
        entry.add_to_hass(hass)

        result = await entry.start_reauth_flow(hass)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        with _patch_validate(return_value={}):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_USERNAME: "auto", CONF_PASSWORD: "fresh"},
            )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "reauth_successful"
        assert entry.data[CONF_PASSWORD] == "fresh"

    async def test_reauth_shows_error_on_invalid_credentials(
        self, hass: HomeAssistant
    ) -> None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id=VALID_INPUT[CONF_URL].lower(),
            data=VALID_INPUT,
        )
        entry.add_to_hass(hass)

        result = await entry.start_reauth_flow(hass)
        with _patch_validate(side_effect=CheckmkAuthError("bad")):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_USERNAME: "auto", CONF_PASSWORD: "wrong"},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}
        # Entry must not be updated until the new credentials validate.
        assert entry.data[CONF_PASSWORD] == "secret"


class TestOptionsFlow:
    async def test_options_round_trip(self, hass: HomeAssistant) -> None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id=VALID_INPUT[CONF_URL].lower(),
            data=VALID_INPUT,
            options={},
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {"scan_interval": 120, "create_metric_sensors": False},
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert entry.options == {
            "scan_interval": 120,
            "create_metric_sensors": False,
        }
