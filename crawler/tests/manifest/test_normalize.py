"""Tests for canonical URL derivation."""

from tapio_crawler.manifest.normalize import canonicalize_url


def test_lowercases_scheme_and_host() -> None:
    """Scheme and host are lowercased; path casing is preserved."""
    assert canonicalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"


def test_strips_default_port() -> None:
    """The default port for the scheme is stripped from the netloc."""
    assert canonicalize_url("https://example.com:443/path") == "https://example.com/path"


def test_keeps_non_default_port() -> None:
    """A non-default port is kept in the netloc."""
    assert canonicalize_url("https://example.com:8080/path") == "https://example.com:8080/path"


def test_drops_fragment() -> None:
    """The URL fragment is dropped from the canonical form."""
    assert canonicalize_url("https://example.com/path#section") == ("https://example.com/path")


def test_strips_utm_tracking_parameters() -> None:
    """Query parameters with a ``utm_`` prefix are removed."""
    url = "https://example.com/path?utm_source=x&id=1&utm_campaign=y"

    assert canonicalize_url(url) == "https://example.com/path?id=1"


def test_strips_known_tracking_parameter_names() -> None:
    """Query parameters matching a known tracking name are removed."""
    url = "https://example.com/path?gclid=abc&id=1"

    assert canonicalize_url(url) == "https://example.com/path?id=1"


def test_defaults_empty_path_to_root() -> None:
    """A URL with no path canonicalizes to a root path of ``/``."""
    assert canonicalize_url("https://example.com") == "https://example.com/"


def test_preserves_ipv6_brackets_with_non_default_port() -> None:
    """IPv6 host brackets are kept when a non-default port is present."""
    assert canonicalize_url("https://[::1]:8443/path") == "https://[::1]:8443/path"


def test_preserves_ipv6_brackets_with_default_port() -> None:
    """IPv6 host brackets are kept even after the default port is stripped."""
    assert canonicalize_url("https://[::1]:443/path") == "https://[::1]/path"
