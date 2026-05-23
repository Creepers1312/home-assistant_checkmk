"""Test bootstrap for the Checkmk custom component.

Pulling in the upstream plugin gives us the ``hass`` fixture for any future
test that needs a real Home Assistant runtime, and ensures the ``homeassistant``
package is importable (which the ``custom_components.checkmk`` package init
relies on).
"""

from __future__ import annotations

pytest_plugins = ["pytest_homeassistant_custom_component"]
