"""Tests for the date and time awareness tool."""

from datetime import UTC
from unittest.mock import patch
from zoneinfo import ZoneInfoNotFoundError

from app.tools.datetime_tool import _get_helsinki_tz, get_current_datetime


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
