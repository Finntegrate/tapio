"""Tests for domain/path scope evaluation."""

from tapio_crawler.config.config_models import ScopeConfig
from tapio_crawler.discovery.scope import evaluate_scope


def test_rejects_url_outside_allowed_domains() -> None:
    """A URL whose host is not in ``allowed_domains`` is rejected."""
    scope = ScopeConfig(allowed_domains=["migri.fi"])

    decision = evaluate_scope("https://evil.example/en/page", scope)

    assert decision.eligible is False
    assert decision.reason == "domain_not_allowed"


def test_accepts_url_within_allowed_domains() -> None:
    """A URL whose host is in ``allowed_domains`` is accepted."""
    scope = ScopeConfig(allowed_domains=["migri.fi"])

    decision = evaluate_scope("https://migri.fi/en/page", scope)

    assert decision.eligible is True


def test_rejects_url_matching_exclude_pattern() -> None:
    """A URL matching an exclude pattern is rejected."""
    scope = ScopeConfig(exclude_url_patterns=["*/search*"])

    decision = evaluate_scope("https://migri.fi/en/search", scope)

    assert decision.eligible is False
    assert decision.reason == "excluded_by_pattern"


def test_rejects_url_with_tracking_query_pattern() -> None:
    """A URL matching an exclude pattern on its query string is rejected."""
    scope = ScopeConfig(exclude_url_patterns=["*?*utm_*"])

    decision = evaluate_scope("https://migri.fi/en/page?utm_source=x", scope)

    assert decision.eligible is False


def test_no_configured_rules_accepts_everything() -> None:
    """With no scope rules configured, every URL is accepted."""
    decision = evaluate_scope("https://anything.example/path", ScopeConfig())

    assert decision.eligible is True
