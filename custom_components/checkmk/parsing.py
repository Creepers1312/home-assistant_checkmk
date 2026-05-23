"""Pure helpers that have no Home Assistant dependencies."""

from __future__ import annotations

import re
from typing import Any

# Number followed by an optional unit, e.g. "0.05ms", "90%", "1024".
_PERF_VALUE = re.compile(r"^(-?[0-9]*\.?[0-9]+)\s*(.*)$")


def parse_perf_data(perf_data: Any) -> dict[str, tuple[float, str | None]]:
    """Parse a Checkmk ``perf_data`` field into ``{metric: (value, unit)}``.

    Each performance-data token has the format ``name=value[unit][;...]``.
    Tokens without a parsable value are silently skipped.
    """
    result: dict[str, tuple[float, str | None]] = {}
    if not perf_data:
        return result

    if isinstance(perf_data, str):
        tokens = perf_data.split()
    elif isinstance(perf_data, (list, tuple)):
        tokens = [str(token) for token in perf_data]
    else:
        return result

    for token in tokens:
        name, sep, rest = token.partition("=")
        if not sep or not name:
            continue
        match = _PERF_VALUE.match(rest.split(";")[0])
        if not match:
            continue
        result[name] = (float(match.group(1)), match.group(2) or None)
    return result


def is_problem(entry: dict[str, Any]) -> bool:
    """Return True if ``entry`` represents an unhandled monitoring problem.

    A "problem" is a non-OK state that has neither been acknowledged nor
    masked by a scheduled downtime.
    """
    return bool(
        entry.get("state")
        and not entry.get("acknowledged")
        and not entry.get("scheduled_downtime_depth")
    )
