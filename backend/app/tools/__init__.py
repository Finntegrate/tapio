"""Tool registry package for Tapio's agent tools."""

from app.config.tool_settings import CostTier, ToolSettings
from app.tools.datetime_tool import add_business_days, add_calendar_days, get_current_datetime
from app.tools.registry import ToolRegistry, ToolSpec

# Every tool Tapio knows about. Adding one here, with its cost tier and any env vars
# it needs, is the only code change; whether it's available is configuration.
TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(get_current_datetime, CostTier.FREE),
    ToolSpec(add_calendar_days, CostTier.FREE),
    ToolSpec(add_business_days, CostTier.FREE),
)

ALL_TOOLS = [spec.tool for spec in TOOL_SPECS]


def build_tool_registry(settings: ToolSettings | None = None) -> ToolRegistry:
    """Build the registry of every known tool under the current configuration.

    Args:
        settings: Optional settings; defaults to reading ``TAPIO_TOOLS_*`` from the environment.

    Returns:
        A registry whose ``tools()`` are the ones this deployment may use.
    """
    return ToolRegistry(TOOL_SPECS, settings)


__all__ = [
    "ALL_TOOLS",
    "TOOL_SPECS",
    "CostTier",
    "ToolRegistry",
    "ToolSettings",
    "ToolSpec",
    "add_business_days",
    "add_calendar_days",
    "build_tool_registry",
    "get_current_datetime",
]
