"""Tests for the pure parsing helpers."""

from __future__ import annotations

import pytest

from custom_components.checkmk.parsing import (
    extract_macs,
    is_problem,
    matches_filter,
    parse_pattern_list,
    parse_perf_data,
)


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


class TestParsePatternList:
    def test_empty_or_none_returns_empty_list(self) -> None:
        assert parse_pattern_list("") == []
        assert parse_pattern_list(None) == []
        assert parse_pattern_list([]) == []

    def test_splits_lines_and_strips(self) -> None:
        text = "  web-*\n\n  db-*  \nlb-?\n"
        assert parse_pattern_list(text) == ["web-*", "db-*", "lb-?"]

    def test_accepts_list_input(self) -> None:
        assert parse_pattern_list([" web ", "", "db"]) == ["web", "db"]


class TestMatchesFilter:
    def test_no_filters_matches_everything(self) -> None:
        assert matches_filter("anything", [], []) is True

    def test_include_only_drops_non_matches(self) -> None:
        assert matches_filter("web-01", ["web-*"], []) is True
        assert matches_filter("db-01", ["web-*"], []) is False

    def test_exclude_drops_match(self) -> None:
        assert matches_filter("ntp", [], ["ntp"]) is False
        assert matches_filter("cpu", [], ["ntp"]) is True

    def test_exclude_wins_over_include(self) -> None:
        # An include of ``*`` should still let the exclude drop the entry.
        assert matches_filter("ntp", ["*"], ["ntp"]) is False

    def test_glob_chars_supported(self) -> None:
        assert matches_filter("eth0", ["eth?"], []) is True
        assert matches_filter("vlan0", ["[ev]th?"], []) is False
        assert matches_filter("Filesystem /var", ["Filesystem *"], []) is True

    def test_match_is_case_sensitive(self) -> None:
        # Checkmk host/service names are case-sensitive; the filter mirrors that.
        assert matches_filter("WEB-01", ["web-*"], []) is False


class TestExtractMacs:
    def test_lnx_if_plugin_output(self) -> None:
        # The exact format reported by the Linux interface check.
        service = {
            "plugin_output": (
                "[ens34], (up), MAC: 00:0C:29:6D:C5:A9, Speed: 10 GBit/s, "
                "In: 144 B/s (<0.01%), Out: 515 B/s (<0.01%)"
            )
        }
        assert extract_macs([service]) == {"00:0c:29:6d:c5:a9"}

    def test_winperf_if_hyphen_format_is_normalised(self) -> None:
        # Windows interface checks historically use hyphen separators; the
        # helper must normalise these to the colon form HA expects.
        service = {"plugin_output": "[Ethernet 2] MAC: 00-0C-29-6D-C5-A9, up"}
        assert extract_macs([service]) == {"00:0c:29:6d:c5:a9"}

    def test_multiple_interfaces_collect_all_macs(self) -> None:
        services = [
            {"plugin_output": "[eth0], (up), MAC: aa:bb:cc:dd:ee:01"},
            {"plugin_output": "[eth1], (up), MAC: aa:bb:cc:dd:ee:02"},
        ]
        assert extract_macs(services) == {
            "aa:bb:cc:dd:ee:01",
            "aa:bb:cc:dd:ee:02",
        }

    def test_duplicate_macs_are_deduplicated(self) -> None:
        services = [
            {"plugin_output": "MAC: aa:bb:cc:dd:ee:01"},
            {"plugin_output": "MAC: AA:BB:CC:DD:EE:01"},
        ]
        assert extract_macs(services) == {"aa:bb:cc:dd:ee:01"}

    def test_placeholder_mac_is_dropped(self) -> None:
        # 00:00:00:00:00:00 would falsely link every host that reports it.
        service = {"plugin_output": "MAC: 00:00:00:00:00:00"}
        assert extract_macs([service]) == set()

    def test_services_without_mac_are_ignored(self) -> None:
        services = [
            {"plugin_output": "Total CPU: 5.10%"},
            {"plugin_output": "Used: 6.83% - 398 GiB of 5.69 TiB"},
            {"plugin_output": None},
            {},
        ]
        assert extract_macs(services) == set()

    def test_empty_input(self) -> None:
        assert extract_macs([]) == set()

    def test_non_dict_entries_are_skipped(self) -> None:
        # Defensive: the coordinator should always hand us dicts, but the
        # helper must not crash if anything else slips through.
        assert extract_macs([None, "not a dict", 42]) == set()
