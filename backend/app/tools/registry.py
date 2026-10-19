"""Config-driven tool registry with a cost guard (#17).

Mirrors the configurable LLM provider pattern (``app.config.llm_settings``): which
tools an agent gets is decided by environment variables, not code. A tool is
available only if it isn't listed in ``TAPIO_TOOLS_DISABLED``, its cost tier is
within ``TAPIO_TOOLS_MAX_COST_TIER``, and every env var it needs (e.g. an API key)
is set. Each available tool is handed out as a copy carrying a callback that logs
its name and cost tier on every call, so tool spend is visible in the logs.
"""

import logging
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.tools import BaseTool

from app.config.tool_settings import CostTier, ToolSettings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A tool plus what it costs and what it needs to run.

    Args:
        tool: The LangChain tool.
        cost_tier: What a call costs (see ``CostTier``).
        required_env_vars: Env vars that must all be set for the tool to be available,
            e.g. the API key of the service it calls.
    """

    tool: BaseTool
    cost_tier: CostTier
    required_env_vars: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        """The tool's name, as the model sees it."""
        return self.tool.name


class _ToolInvocationLogger(BaseCallbackHandler):
    """Log each tool call's name and cost tier; never its input, which may contain user text."""

    def __init__(self, spec: ToolSpec) -> None:
        self._spec = spec

    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:  # noqa: ARG002
        """Log that the tool was called, with its cost tier."""
        logger.info("Tool %s invoked (cost tier: %s)", self._spec.name, self._spec.cost_tier.value)


class ToolRegistry:
    """Resolve which registered tools are available under the current configuration.

    Args:
        specs: Every tool Tapio knows about.
        settings: Which tools are switched off and the maximum allowed cost tier.
        environ: Where to look up each tool's required env vars; defaults to ``os.environ``.

    Raises:
        ValueError: If two specs share a name, or ``settings.disabled`` names an unknown tool.
    """

    def __init__(
        self,
        specs: Iterable[ToolSpec],
        settings: ToolSettings | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        """Index the specs by name and validate ``settings`` against them.

        Args:
            specs: Every tool Tapio knows about.
            settings: Which tools are switched off and the maximum allowed cost tier.
            environ: Where to look up each tool's required env vars; defaults to ``os.environ``.

        Raises:
            ValueError: If two specs share a name, or ``settings.disabled`` names an unknown tool.
        """
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            if spec.name in self._specs:
                msg = f"Tool {spec.name!r} is registered twice"
                raise ValueError(msg)
            self._specs[spec.name] = spec
        self._settings = settings or ToolSettings()
        self._environ = os.environ if environ is None else environ

        unknown = sorted(set(self._settings.disabled) - set(self._specs))
        if unknown:
            msg = f"Unknown TAPIO_TOOLS_DISABLED names {unknown}; expected any of {sorted(self._specs)}"
            raise ValueError(msg)

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        """Every registered tool, available or not."""
        return tuple(self._specs.values())

    def unavailable_reason(self, name: str) -> str | None:
        """Why a registered tool is unavailable, or ``None`` if it is available.

        Args:
            name: A registered tool's name.

        Returns:
            A short reason, or ``None``.
        """
        spec = self._specs[name]
        if name in self._settings.disabled:
            return "disabled by TAPIO_TOOLS_DISABLED"
        if spec.cost_tier.rank > self._settings.max_cost_tier.rank:
            return f"cost tier {spec.cost_tier.value} exceeds TAPIO_TOOLS_MAX_COST_TIER"
        missing = [var for var in spec.required_env_vars if not self._environ.get(var)]
        if missing:
            return f"missing env vars {missing}"
        return None

    def tools(self) -> list[BaseTool]:
        """Return the available tools, each logging its calls with its cost tier.

        Returns:
            Copies of the available tools, so the module-level tool objects stay untouched.
        """
        available = []
        for spec in self._specs.values():
            reason = self.unavailable_reason(spec.name)
            if reason:
                logger.info("Tool %s unavailable: %s", spec.name, reason)
                continue
            callbacks = [*(spec.tool.callbacks or []), _ToolInvocationLogger(spec)]  # type: ignore[misc]
            available.append(spec.tool.model_copy(update={"callbacks": callbacks}))
        return available
