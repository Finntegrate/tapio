"""Tests for the per-provider configuration table (#146, #164)."""

from typing import Any

import pytest

from app.services.llm_providers import PROVIDERS, ProviderConfig, apply_timeout


class TestApplyTimeout:
    """Tests for wiring a request timeout into a provider's constructor kwargs."""

    def test_a_provider_with_a_top_level_timeout_kwarg_takes_it_directly(self) -> None:
        kwargs: dict[str, Any] = {}

        apply_timeout(PROVIDERS["openai"], kwargs, 30.0)

        assert kwargs == {"timeout": 30.0}

    def test_a_provider_without_one_nests_it_under_client_kwargs(self) -> None:
        """ChatOllama has no top-level timeout field — its httpx client takes one."""
        kwargs: dict[str, Any] = {}

        apply_timeout(PROVIDERS["ollama"], kwargs, 30.0)

        assert kwargs == {"client_kwargs": {"timeout": 30.0}}

    def test_a_provider_without_a_table_entry_takes_a_top_level_timeout(self) -> None:
        """A provider LangChain supports but Tapio doesn't configure gets the common case."""
        kwargs: dict[str, Any] = {}

        apply_timeout(None, kwargs, 30.0)

        assert kwargs == {"timeout": 30.0}

    def test_the_wiring_comes_from_the_table_entry(self) -> None:
        """The nesting is the provider's own quirk, not a hardcoded provider name."""
        provider = ProviderConfig(model_type=PROVIDERS["ollama"].model_type, timeout_kwarg=None)
        kwargs: dict[str, Any] = {}

        apply_timeout(provider, kwargs, 30.0)

        assert kwargs == {"client_kwargs": {"timeout": 30.0}}

    @pytest.mark.parametrize("provider_name", sorted(PROVIDERS))
    def test_every_configured_provider_wires_the_timeout_one_way(self, provider_name: str) -> None:
        kwargs: dict[str, Any] = {}

        apply_timeout(PROVIDERS[provider_name], kwargs, 30.0)

        assert kwargs in ({"timeout": 30.0}, {"client_kwargs": {"timeout": 30.0}})
