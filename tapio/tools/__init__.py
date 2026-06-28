"""Tool registry package for Tapio's agent tools."""
from tapio.tools.datetime_tool import get_current_datetime

ALL_TOOLS = [get_current_datetime]
__all__ = ["ALL_TOOLS", "get_current_datetime"]
