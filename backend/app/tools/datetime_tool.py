"""Date and time awareness tool for the agent."""

from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import holidays
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


# Finnish public holidays from the open-source `holidays` package (no API, no fees). It
# computes them by rule, including Easter-based dates, for 1853-2100. Its calendar also
# counts Midsummer Eve and Christmas Eve, as does Finland's Act on the Calculation of
# Statutory Time Limits (150/1930), which moves a deadline falling on a Saturday,
# Sunday, public holiday, Independence Day, May Day, Midsummer Eve, or Christmas Eve to
# the next working day.
_FINNISH_HOLIDAYS = holidays.Finland(language="en_US")

# The longest count accepted, about ten years of working days: enough for any
# immigration deadline, and a bound on the day-by-day walk.
_MAX_BUSINESS_DAYS = 2600

_SATURDAY = 5


def _is_business_day(day: date) -> bool:
    return day.weekday() < _SATURDAY and day not in _FINNISH_HOLIDAYS


@tool
def add_business_days(start_date: str, days: int) -> str:
    """Add or subtract Finnish working days from a date.

    Use this tool for deadlines counted in working days ("arkipäivä"), such as "within
    14 working days of the decision". It skips Saturdays, Sundays, and Finnish public
    holidays, including Midsummer Eve and Christmas Eve. For deadlines in plain calendar
    days, use add_calendar_days instead. Counting starts from the day after start_date;
    pass a negative number to count backwards.

    Args:
        start_date: The starting date in ISO format, YYYY-MM-DD, e.g. "2026-04-01".
        days: Number of working days to add. Negative values subtract.

    Returns:
        The resulting date as a human-readable string, plus any holidays that were
        skipped, e.g. "Wednesday, 08 April 2026 (skipped holidays: Good Friday 03 April,
        Easter Monday 06 April)", or an error message if start_date is not a valid
        YYYY-MM-DD date or the count or result is out of range.
    """
    try:
        current = date.fromisoformat(start_date)
    except ValueError:
        return f"Invalid date '{start_date}'. Use the format YYYY-MM-DD, e.g. 2026-04-01."
    if abs(days) > _MAX_BUSINESS_DAYS:
        return f"Counts of more than {_MAX_BUSINESS_DAYS} working days are not supported."

    step = timedelta(days=1 if days >= 0 else -1)
    remaining = abs(days)
    skipped: list[date] = []
    try:
        while remaining:
            current += step
            if not _FINNISH_HOLIDAYS.start_year <= current.year <= _FINNISH_HOLIDAYS.end_year:
                return "The resulting date is outside the years the Finnish holiday calendar covers (1853-2100)."
            if _is_business_day(current):
                remaining -= 1
            elif current.weekday() < _SATURDAY:
                skipped.append(current)
    except OverflowError:
        return "The resulting date is out of the supported range."

    result = current.strftime("%A, %d %B %Y")
    if not skipped:
        return result
    names = ", ".join(f"{_FINNISH_HOLIDAYS.get(day)} {day.strftime('%d %B')}" for day in sorted(skipped))
    return f"{result} (skipped holidays: {names})"
