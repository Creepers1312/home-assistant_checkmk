"""Config and options flow for the Checkmk integration."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
)

from .api import CheckmkAuthError, CheckmkClient, CheckmkConnectionError
from .const import (
    CONF_CREATE_METRIC_SENSORS,
    CONF_HOST_EXCLUDE,
    CONF_HOST_INCLUDE,
    CONF_SERVICE_EXCLUDE,
    CONF_SERVICE_INCLUDE,
    DEFAULT_CREATE_METRIC_SENSORS,
    DEFAULT_PATTERN_LIST,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_VERIFY_SSL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)

_PATTERN_SELECTOR = TextSelector(TextSelectorConfig(multiline=True))

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_VERIFY_SSL, default=DEFAULT_VERIFY_SSL): bool,
    }
)


async def _validate_input(hass, data: Mapping[str, Any]) -> None:
    """Validate that the credentials can talk to Checkmk."""
    session = async_get_clientsession(
        hass, verify_ssl=data.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)
    )
    client = CheckmkClient(
        session,
        data[CONF_URL],
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
    )
    await client.async_validate()


class CheckmkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the UI configuration flow for Checkmk."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            await self.async_set_unique_id(url.lower())
            self._abort_if_unique_id_configured()

            errors = await self._try_connect(user_input)
            if not errors:
                return self.async_create_entry(
                    title=url, data={**user_input, CONF_URL: url}
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start the re-authentication flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm new credentials for an existing entry."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()

        if user_input is not None:
            merged = {**entry.data, **user_input}
            errors = await self._try_connect(merged)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=merged)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def _try_connect(self, data: Mapping[str, Any]) -> dict[str, str]:
        """Attempt a connection and return a mapping of errors."""
        try:
            await _validate_input(self.hass, data)
        except CheckmkAuthError:
            return {"base": "invalid_auth"}
        except CheckmkConnectionError:
            return {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error validating Checkmk connection")
            return {"base": "unknown"}
        return {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Return the options flow handler."""
        return CheckmkOptionsFlow()


class CheckmkOptionsFlow(OptionsFlow):
    """Handle the Checkmk options flow."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the integration options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Clamp(min=MIN_SCAN_INTERVAL)),
                vol.Optional(
                    CONF_CREATE_METRIC_SENSORS,
                    default=options.get(
                        CONF_CREATE_METRIC_SENSORS, DEFAULT_CREATE_METRIC_SENSORS
                    ),
                ): bool,
                vol.Optional(
                    CONF_HOST_INCLUDE,
                    default=options.get(CONF_HOST_INCLUDE, DEFAULT_PATTERN_LIST),
                ): _PATTERN_SELECTOR,
                vol.Optional(
                    CONF_HOST_EXCLUDE,
                    default=options.get(CONF_HOST_EXCLUDE, DEFAULT_PATTERN_LIST),
                ): _PATTERN_SELECTOR,
                vol.Optional(
                    CONF_SERVICE_INCLUDE,
                    default=options.get(
                        CONF_SERVICE_INCLUDE, DEFAULT_PATTERN_LIST
                    ),
                ): _PATTERN_SELECTOR,
                vol.Optional(
                    CONF_SERVICE_EXCLUDE,
                    default=options.get(
                        CONF_SERVICE_EXCLUDE, DEFAULT_PATTERN_LIST
                    ),
                ): _PATTERN_SELECTOR,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
