"""Canonical URL derivation for manifest identity.

Which query parameters are meaningful versus tracking-only is an explicit
open question per docs/specs/crawler-improvements.md ("begin conservatively
and add reviewed exceptions"); this strips a small, conservative built-in
set of well-known tracking parameters rather than trying to infer stripping
rules from each source's URL-scope glob patterns.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}

_TRACKING_PARAM_PREFIXES = ("utm_", "mc_")
_TRACKING_PARAM_NAMES = frozenset({"gclid", "fbclid", "msclkid", "_ga", "ref"})


def canonicalize_url(url: str) -> str:
    """Derive a stable, deduplicated canonical form of ``url``.

    Lowercases scheme and host, strips a default port, drops the fragment,
    and removes known tracking query parameters.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    hostname = (parts.hostname or "").lower()
    port = parts.port
    netloc = hostname
    if port is not None and port != _DEFAULT_PORTS.get(scheme):
        netloc = f"{hostname}:{port}"

    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(key)
    ]
    query = urlencode(query_pairs)
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, query, ""))


def _is_tracking_param(key: str) -> bool:
    lowered = key.lower()
    return lowered in _TRACKING_PARAM_NAMES or lowered.startswith(
        _TRACKING_PARAM_PREFIXES,
    )
