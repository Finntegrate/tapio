"""Tests for the date and time awareness tool."""

from datetime import UTC
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

from app.tools.datetime_tool import _get_helsinki_tz, add_calendar_days, get_current_datetime


def test_returns_a_non_empty_string() -> None:
    """The tool always produces some human-readable output."""
    result = get_current_datetime.invoke({})

    assert isinstance(result, str)
    assert len(result) > 0


def test_includes_a_helsinki_timezone_abbreviation() -> None:
    """The normal path reports actual Helsinki time, not a silent UTC fallback."""
    result = get_current_datetime.invoke({})

    assert "EET" in result or "EEST" in result


def test_falls_back_to_utc_when_helsinki_tz_data_is_unavailable() -> None:
    """The fallback path is covered separately, so the normal-path test can stay strict."""
    with patch("app.tools.datetime_tool.ZoneInfo", side_effect=ZoneInfoNotFoundError):
        assert _get_helsinki_tz() is UTC


def test_adds_days_within_a_month() -> None:
    """Adding days inside one month keeps the same month."""
    result = add_calendar_days.invoke({"start_date": "2026-06-10", "days": 5})

    assert result == "Monday, 15 June 2026"


def test_adds_days_across_a_month_boundary() -> None:
    """Adding days rolls over into the next month."""
    result = add_calendar_days.invoke({"start_date": "2026-06-27", "days": 90})

    assert result == "Friday, 25 September 2026"


def test_adds_days_across_a_year_boundary() -> None:
    """Adding days rolls over into the next year."""
    result = add_calendar_days.invoke({"start_date": "2026-12-20", "days": 30})

    assert result == "Tuesday, 19 January 2027"


def test_subtracts_days_with_a_negative_number() -> None:
    """A negative count moves the date backwards."""
    result = add_calendar_days.invoke({"start_date": "2026-03-10", "days": -15})

    assert result == "Monday, 23 February 2026"


def test_subtracts_days_across_a_year_boundary() -> None:
    """Subtracting days rolls back into the previous year."""
    result = add_calendar_days.invoke({"start_date": "2027-01-05", "days": -10})

    assert result == "Saturday, 26 December 2026"


def test_handles_leap_day() -> None:
    """Leap years are counted correctly."""
    result = add_calendar_days.invoke({"start_date": "2028-02-28", "days": 1})

    assert result == "Tuesday, 29 February 2028"


def test_zero_days_returns_the_same_date() -> None:
    """Adding zero days does not change the date."""
    result = add_calendar_days.invoke({"start_date": "2026-06-27", "days": 0})

    assert result == "Saturday, 27 June 2026"


def test_invalid_date_returns_an_error_message() -> None:
    """Bad input yields a readable message instead of raising."""
    result = add_calendar_days.invoke({"start_date": "27/06/2026", "days": 5})

    assert "Invalid date" in result


def test_out_of_range_result_returns_an_error_message() -> None:
    """Results beyond the supported date range are reported, not raised."""
    result = add_calendar_days.invoke({"start_date": "9999-12-31", "days": 1})

    assert "out of the supported range" in result
