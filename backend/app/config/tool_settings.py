"""Environment-driven agent tool configuration (#17)."""

from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


class CostTier(StrEnum):
    """What calling a tool costs, cheapest first.

    ``free`` costs nothing per call. ``metered`` is billed per call or per unit but
    bounded (e.g. a capped API quota). ``paid`` is billed per call with no cap of its own.
    """

    FREE = "free"
    METERED = "metered"
    PAID = "paid"

    @property
    def rank(self) -> int:
        """Position in cheapest-first order, for comparing tiers."""
        return list(CostTier).index(self)


class ToolSettings(BaseSettings):
    """Which agent tools are switched on, without a code change.

    Args:
        disabled: Tool names to switch off, read from ``TAPIO_TOOLS_DISABLED`` as a JSON
            list (e.g. ``'["add_calendar_days"]'``). An unknown name fails at startup.
        max_cost_tier: The most expensive tier allowed, from ``TAPIO_TOOLS_MAX_COST_TIER``.
            Defaults to ``free`` so a deployment never spends money on tools unless an
            operator opts in.
    """

    model_config = SettingsConfigDict(env_prefix="TAPIO_TOOLS_")

    disabled: list[str] = []
    max_cost_tier: CostTier = CostTier.FREE
