"""Constants for the Checkmk integration."""

from __future__ import annotations

DOMAIN = "checkmk"

# Config / options keys
CONF_CREATE_METRIC_SENSORS = "create_metric_sensors"

# Defaults
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 15
DEFAULT_VERIFY_SSL = True
DEFAULT_CREATE_METRIC_SENSORS = True

# State mappings (Livestatus numeric states -> readable strings)
HOST_STATE: dict[int, str] = {
    0: "up",
    1: "down",
    2: "unreachable",
}

SERVICE_STATE: dict[int, str] = {
    0: "ok",
    1: "warning",
    2: "critical",
    3: "unknown",
}
