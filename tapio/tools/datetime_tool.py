from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from langchain_core.tools import tool

# TODO: Get user timezone via UI or setting, since not all users are in Finland
HELSINKI_TZ = ZoneInfo("Europe/Helsinki")


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
    now = datetime.now(timezone.utc).astimezone(HELSINKI_TZ)
    return now.strftime("%A, %d %B %Y, %H:%M %Z")