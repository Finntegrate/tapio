"""Tool registry package for Tapio's agent tools."""

from app.tools.datetime_tool import add_calendar_days, get_current_datetime

ALL_TOOLS = [get_current_datetime, add_calendar_days]

__all__ = ["ALL_TOOLS", "add_calendar_days", "get_current_datetime"]
