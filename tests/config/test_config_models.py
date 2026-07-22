"""Tests for the configuration data models."""

import pytest

from tapio.config.config_models import (
    CrawlerConfig,
    ParserConfigRegistry,
    SiteConfig,
)


class TestCrawlerConfig:
    """Tests for the CrawlerConfig model."""

    def test_default_values(self) -> None:
        config = CrawlerConfig()

        assert config.max_depth == 1
        assert config.limit == 100
        assert config.render is True
        assert config.source == "all"

    def test_custom_values(self) -> None:
        config = CrawlerConfig(
            max_depth=3,
            limit=500,
            render=False,
            source="sitemaps",
        )

        assert config.max_depth == 3
        assert config.limit == 500
        assert config.render is False
        assert config.source == "sitemaps"

    def test_max_depth_validation(self) -> None:
        with pytest.raises(ValueError):
            CrawlerConfig(max_depth=0)
        with pytest.raises(ValueError):
            CrawlerConfig(max_depth=11)

    def test_limit_validation(self) -> None:
        with pytest.raises(ValueError):
            CrawlerConfig(limit=0)
        with pytest.raises(ValueError):
            CrawlerConfig(limit=100_001)

    def test_source_validation(self) -> None:
        with pytest.raises(ValueError):
            CrawlerConfig(source="invalid")


class TestSiteConfig:
    """Tests for the SiteConfig model."""

    def test_minimal_config(self) -> None:
        config = SiteConfig(base_url="https://example.com")

        assert str(config.base_url) == "https://example.com/"
        assert config.description is None
        assert isinstance(config.crawler_config, CrawlerConfig)

    def test_full_config(self) -> None:
        config = SiteConfig(
            base_url="https://example.com",
            description="Example site",
            crawler_config=CrawlerConfig(max_depth=2, limit=50, render=False, source="sitemaps"),
        )

        assert config.description == "Example site"
        assert config.crawler_config.max_depth == 2
        assert config.crawler_config.limit == 50
        assert config.crawler_config.render is False
        assert config.crawler_config.source == "sitemaps"

    def test_base_dir_from_url(self) -> None:
        config = SiteConfig(base_url="https://example.com/en")

        assert config.base_dir == "example.com"

    def test_invalid_url_raises_error(self) -> None:
        with pytest.raises(ValueError):
            SiteConfig(base_url="not a url")


class TestParserConfigRegistry:
    """Tests for the site config registry."""

    def test_empty_registry(self) -> None:
        registry = ParserConfigRegistry(sites={})

        assert registry.sites == {}

    def test_with_sites(self) -> None:
        registry = ParserConfigRegistry(
            sites={
                "site1": SiteConfig(base_url="https://site1.com"),
                "site2": SiteConfig(base_url="https://site2.com"),
            },
        )

        assert "site1" in registry.sites
        assert "site2" in registry.sites
        assert len(registry.sites) == 2