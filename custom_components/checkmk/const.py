"""Constants for the Checkmk integration."""

from __future__ import annotations

DOMAIN = "checkmk"

# Config / options keys
CONF_CREATE_METRIC_SENSORS = "create_metric_sensors"
CONF_HOST_INCLUDE = "host_include"
CONF_HOST_EXCLUDE = "host_exclude"
CONF_SERVICE_INCLUDE = "service_include"
CONF_SERVICE_EXCLUDE = "service_exclude"

# Defaults
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 15
DEFAULT_VERIFY_SSL = True
DEFAULT_CREATE_METRIC_SENSORS = True
DEFAULT_PATTERN_LIST = ""

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
