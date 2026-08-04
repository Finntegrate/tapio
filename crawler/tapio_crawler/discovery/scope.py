"""Domain and path scope evaluation for a discovered URL.

Content-type and language eligibility are evaluated at render time (not
here): a URL's content type is only known after a fetch, and language
scope is expressed as a path pattern (see ``ScopeConfig.include_url_patterns``).
"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from urllib.parse import urlsplit

from tapio_crawler.config.config_models import ScopeConfig


@dataclass
class ScopeDecision:
    """Whether one URL is eligible for a source, and why not if not."""

    eligible: bool
    reason: str | None = None


def evaluate_scope(url: str, scope: ScopeConfig) -> ScopeDecision:
    """Return the scope decision for ``url`` under ``scope``'s domain/path rules."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    # Patterns like "/en/*" or "*?*utm_*" are path-relative, not full-URL.
    target = parts.path + (f"?{parts.query}" if parts.query else "")

    if scope.allowed_domains and not any(
        host == domain.lower() for domain in scope.allowed_domains
    ):
        return ScopeDecision(eligible=False, reason="domain_not_allowed")

    if scope.exclude_url_patterns and any(
        fnmatch(target, pattern) for pattern in scope.exclude_url_patterns
    ):
        return ScopeDecision(eligible=False, reason="excluded_by_pattern")

    if scope.include_url_patterns and not any(
        fnmatch(target, pattern) for pattern in scope.include_url_patterns
    ):
        return ScopeDecision(eligible=False, reason="not_in_include_patterns")

    return ScopeDecision(eligible=True)
