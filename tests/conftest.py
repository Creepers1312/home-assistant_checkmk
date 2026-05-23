"""Test bootstrap for the Checkmk custom component."""

from __future__ import annotations

import pytest

pytest_plugins = ["pytest_homeassistant_custom_component"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant discover ``custom_components/checkmk`` during tests.

    Without this, ``homeassistant.loader`` raises ``IntegrationNotFound`` and
    every config-flow / service test fails at startup.
    """
    yield
