"""Tests for the Crawl4AI collection configuration."""

import pytest
from pydantic import HttpUrl, ValidationError

from tapio_crawler.config.config_models import (
    CrawlerConfig,
    MarkdownConfig,
    SiteConfig,
    SiteConfigRegistry,
)


def test_crawler_config_has_safe_defaults() -> None:
    config = CrawlerConfig()

    assert config.max_depth == 1
    assert config.max_pages == 50
    assert config.page_timeout == 30
    assert (config.min_delay, config.max_delay) == (1.0, 3.0)
    assert config.max_concurrent == 3


def test_crawler_config_rejects_invalid_delay_range() -> None:
    with pytest.raises(ValidationError, match="min_delay"):
        CrawlerConfig(min_delay=3.0, max_delay=1.0)


@pytest.mark.parametrize(
    "field,value", [("max_depth", -1), ("max_pages", 0), ("max_concurrent", 0)]
)
def test_crawler_config_enforces_bounds(field: str, value: int) -> None:
    with pytest.raises(ValidationError):
        CrawlerConfig(**{field: value})


def test_site_config_and_registry() -> None:
    config = SiteConfig(base_url=HttpUrl("https://subdomain.example.com:8080"))
    registry = SiteConfigRegistry.model_validate(
        {"sites": {"example": {"base_url": "https://example.com"}}},
    )

    assert config.base_dir == "subdomain.example.com"
    assert isinstance(config.crawler_config.markdown_config, MarkdownConfig)
    assert str(registry.sites["example"].base_url) == "https://example.com/"
