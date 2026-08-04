"""Tests for canonical URL derivation."""

from tapio_crawler.manifest.normalize import canonicalize_url


def test_lowercases_scheme_and_host() -> None:
    assert canonicalize_url("HTTPS://Example.COM/Path") == "https://example.com/Path"


def test_strips_default_port() -> None:
    assert (
        canonicalize_url("https://example.com:443/path") == "https://example.com/path"
    )


def test_keeps_non_default_port() -> None:
    assert (
        canonicalize_url("https://example.com:8080/path")
        == "https://example.com:8080/path"
    )


def test_drops_fragment() -> None:
    assert canonicalize_url("https://example.com/path#section") == (
        "https://example.com/path"
    )


def test_strips_utm_tracking_parameters() -> None:
    url = "https://example.com/path?utm_source=x&id=1&utm_campaign=y"

    assert canonicalize_url(url) == "https://example.com/path?id=1"


def test_strips_known_tracking_parameter_names() -> None:
    url = "https://example.com/path?gclid=abc&id=1"

    assert canonicalize_url(url) == "https://example.com/path?id=1"


def test_defaults_empty_path_to_root() -> None:
    assert canonicalize_url("https://example.com") == "https://example.com/"


def test_preserves_ipv6_brackets_with_non_default_port() -> None:
    assert canonicalize_url("https://[::1]:8443/path") == "https://[::1]:8443/path"


def test_preserves_ipv6_brackets_with_default_port() -> None:
    assert canonicalize_url("https://[::1]:443/path") == "https://[::1]/path"
