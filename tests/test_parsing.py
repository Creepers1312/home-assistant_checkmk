"""Tests for the pure parsing helpers."""

from __future__ import annotations

import pytest

from custom_components.checkmk.parsing import is_problem, parse_perf_data


class TestParsePerfData:
    def test_empty_input_returns_empty_dict(self) -> None:
        assert parse_perf_data("") == {}
        assert parse_perf_data(None) == {}
        assert parse_perf_data([]) == {}

    def test_unsupported_input_type_returns_empty_dict(self) -> None:
        assert parse_perf_data(42) == {}
        assert parse_perf_data({"already": "parsed"}) == {}

    def test_single_metric_without_unit(self) -> None:
        assert parse_perf_data("load1=0.05") == {"load1": (0.05, None)}

    def test_single_metric_with_percent_unit(self) -> None:
        assert parse_perf_data("usage=90%") == {"usage": (90.0, "%")}

    def test_strips_thresholds(self) -> None:
        # Checkmk perf_data tokens often include ``;warn;crit;min;max``.
        result = parse_perf_data("rta=0.123ms;200;500;0")
        assert result == {"rta": (0.123, "ms")}

    def test_multiple_tokens_space_separated(self) -> None:
        result = parse_perf_data("load1=0.1 load5=0.2 load15=0.3")
        assert result == {
            "load1": (0.1, None),
            "load5": (0.2, None),
            "load15": (0.3, None),
        }

    def test_list_input_is_supported(self) -> None:
        result = parse_perf_data(["temp=21.5C", "humidity=55%"])
        assert result == {
            "temp": (21.5, "C"),
            "humidity": (55.0, "%"),
        }

    def test_negative_values(self) -> None:
        assert parse_perf_data("delta=-1.5") == {"delta": (-1.5, None)}

    def test_skips_unparsable_tokens(self) -> None:
        # ``=`` only, empty name, and missing value should all be skipped, while
        # a valid sibling token still ends up in the result.
        result = parse_perf_data("broken =alsobroken ok=1.0")
        assert result == {"ok": (1.0, None)}

    def test_returns_last_value_when_name_repeats(self) -> None:
        # Checkmk shouldn't normally do this, but we should at least not crash.
        result = parse_perf_data("x=1 x=2")
        assert result == {"x": (2.0, None)}


class TestIsProblem:
    def test_ok_state_is_not_problem(self) -> None:
        assert is_problem({"state": 0}) is False

    def test_missing_state_treated_as_ok(self) -> None:
        assert is_problem({}) is False

    def test_warning_with_no_handling_is_problem(self) -> None:
        assert is_problem({"state": 1}) is True

    def test_critical_with_ack_is_not_problem(self) -> None:
        assert is_problem({"state": 2, "acknowledged": 1}) is False

    def test_critical_in_downtime_is_not_problem(self) -> None:
        assert is_problem({"state": 2, "scheduled_downtime_depth": 1}) is False

    @pytest.mark.parametrize("state", [1, 2, 3])
    def test_all_non_ok_states_are_problems(self, state: int) -> None:
        assert is_problem({"state": state}) is True
