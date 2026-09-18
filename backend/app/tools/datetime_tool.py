"""Date and time awareness tool for the agent."""

from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool


def _get_helsinki_tz() -> tzinfo:
    """Return the Helsinki timezone, falling back to UTC if tz data is unavailable.

    Returns:
        The Europe/Helsinki zone, or UTC if the runtime has no tz database.
    """
    try:
        return ZoneInfo("Europe/Helsinki")
    except ZoneInfoNotFoundError:
        return UTC


@tool
def get_current_datetime() -> str:
    """Return the current date and time in Helsinki (Finnish) local time.

    Use this tool whenever the user's question involves today's date, current
    deadlines, permit processing windows, office opening hours, or any other
    context that requires knowing what day or time it is right now.

    Returns:
        A human-readable string with the current weekday, date, and time in
        Helsinki local time, e.g. "Tuesday, 27 June 2026, 14:32 EEST".
    """
    now = datetime.now(UTC).astimezone(_get_helsinki_tz())
    return now.strftime("%A, %d %B %Y, %H:%M %Z")


@tool
def add_calendar_days(start_date: str, days: int) -> str:
    """Add or subtract calendar days from a date.

    Use this tool for deadlines counted in plain calendar days, such as
    "when does my 90-day visa-free period end" or "what is the deadline 30 days
    from my decision date". It counts every day, including weekends and
    holidays. Pass a negative number to count backwards.

    Args:
        start_date: The starting date in ISO format, YYYY-MM-DD, e.g. "2026-06-27".
        days: Number of calendar days to add. Negative values subtract.

    Returns:
        The resulting date as a human-readable string, e.g.
        "Sunday, 27 September 2026", or an error message if start_date is
        not a valid YYYY-MM-DD date or the result is out of range.
    """
    try:
        start = date.fromisoformat(start_date)
        result = start + timedelta(days=days)
    except ValueError:
        return f"Invalid date '{start_date}'. Use the format YYYY-MM-DD, e.g. 2026-06-27."
    except OverflowError:
        return "The resulting date is out of the supported range."
    return result.strftime("%A, %d %B %Y")
