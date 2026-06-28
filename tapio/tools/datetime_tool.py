from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.tools import tool


def _get_helsinki_tz() -> tzinfo:
    try:
        return ZoneInfo("Europe/Helsinki")
    except ZoneInfoNotFoundError:
        return timezone.utc


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
    now = datetime.now(timezone.utc).astimezone(_get_helsinki_tz())
    return now.strftime("%A, %d %B %Y, %H:%M %Z")