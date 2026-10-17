"""Tests for the config-driven tool registry and cost guard (#17)."""

import logging
import re
from pathlib import Path

import pytest
from langchain_core.tools import tool

from app.tools import TOOL_SPECS, CostTier, ToolRegistry, ToolSettings, ToolSpec, build_tool_registry

README = Path(__file__).parents[2] / "README.md"


@tool
def free_tool() -> str:
    """A free test tool."""
    return "free"


@tool
def metered_tool() -> str:
    """A metered test tool."""
    return "metered"


@tool
def paid_tool() -> str:
    """A paid test tool that needs a key."""
    return "paid"


SPECS = (
    ToolSpec(free_tool, CostTier.FREE),
    ToolSpec(metered_tool, CostTier.METERED),
    ToolSpec(paid_tool, CostTier.PAID, required_env_vars=("PAID_API_KEY",)),
)


def _names(registry: ToolRegistry) -> list[str]:
    return [t.name for t in registry.tools()]


def test_defaults_allow_only_free_tools() -> None:
    registry = ToolRegistry(SPECS, ToolSettings(), environ={"PAID_API_KEY": "k"})

    assert _names(registry) == ["free_tool"]
    assert "exceeds" in (registry.unavailable_reason("paid_tool") or "")


def test_raising_the_cost_tier_enables_tools_up_to_it() -> None:
    registry = ToolRegistry(SPECS, ToolSettings(max_cost_tier=CostTier.METERED), environ={"PAID_API_KEY": "k"})

    assert _names(registry) == ["free_tool", "metered_tool"]


def test_a_tool_missing_its_env_var_is_unavailable() -> None:
    registry = ToolRegistry(SPECS, ToolSettings(max_cost_tier=CostTier.PAID), environ={})

    assert _names(registry) == ["free_tool", "metered_tool"]
    assert registry.unavailable_reason("paid_tool") == "missing env vars ['PAID_API_KEY']"


def test_a_disabled_tool_is_unavailable_whatever_its_tier() -> None:
    registry = ToolRegistry(SPECS, ToolSettings(disabled=["free_tool"]), environ={})

    assert _names(registry) == []


def test_settings_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAPIO_TOOLS_DISABLED", '["free_tool"]')
    monkeypatch.setenv("TAPIO_TOOLS_MAX_COST_TIER", "metered")

    assert _names(ToolRegistry(SPECS, environ={})) == ["metered_tool"]


def test_an_unknown_disabled_name_fails_at_startup() -> None:
    with pytest.raises(ValueError, match="Unknown TAPIO_TOOLS_DISABLED"):
        ToolRegistry(SPECS, ToolSettings(disabled=["no_such_tool"]))


def test_a_duplicate_name_fails_at_registration() -> None:
    with pytest.raises(ValueError, match="registered twice"):
        ToolRegistry((*SPECS, ToolSpec(free_tool, CostTier.FREE)))


def test_invocations_are_logged_with_their_tier_but_not_their_input(caplog: pytest.LogCaptureFixture) -> None:
    (logged_tool,) = ToolRegistry(SPECS, ToolSettings(), environ={}).tools()

    with caplog.at_level(logging.INFO, logger="app.tools.registry"):
        assert logged_tool.invoke({}) == "free"

    assert "Tool free_tool invoked (cost tier: free)" in caplog.text


def test_handing_out_tools_leaves_the_module_level_tool_untouched() -> None:
    ToolRegistry(SPECS, ToolSettings(), environ={}).tools()

    assert not free_tool.callbacks


def test_every_shipped_tool_is_available_by_default() -> None:
    assert _names(build_tool_registry(ToolSettings())) == [spec.name for spec in TOOL_SPECS]


def test_readme_documents_every_shipped_tool_with_its_tier() -> None:
    readme = README.read_text(encoding="utf-8")
    for spec in TOOL_SPECS:
        assert re.search(rf"\| `{spec.name}` \| {spec.cost_tier.value} \|", readme), spec.name
