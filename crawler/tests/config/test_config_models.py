"""Tests for the config_models module."""

import pytest
from pydantic import HttpUrl, ValidationError

from tapio_crawler.config.config_models import (
    CrawlerConfig,
    HtmlToMarkdownConfig,
    ParserConfig,
    ParserConfigRegistry,
    SiteConfig,
)


class TestCrawlerConfig:
    """Test the CrawlerConfig model."""

    def test_default_values(self):
        """Test default values for CrawlerConfig."""
        config = CrawlerConfig()
        assert config.delay_between_requests == 1.0
        assert config.max_concurrent == 5
        assert config.max_depth == 1

    def test_custom_values(self):
        """Test CrawlerConfig with custom values."""
        config = CrawlerConfig(
            delay_between_requests=2.5,
            max_concurrent=10,
            max_depth=3,
        )
        assert config.delay_between_requests == 2.5
        assert config.max_concurrent == 10
        assert config.max_depth == 3

    def test_delay_validation(self):
        """Test that delay_between_requests must be non-negative."""
        # Valid values
        config = CrawlerConfig(delay_between_requests=0.0)
        assert config.delay_between_requests == 0.0

        # Invalid negative value
        with pytest.raises(ValidationError):
            CrawlerConfig(delay_between_requests=-1.0)

    def test_max_concurrent_validation(self):
        """Test that max_concurrent must be within valid range."""
        # Valid values
        config = CrawlerConfig(max_concurrent=1)
        assert config.max_concurrent == 1

        config = CrawlerConfig(max_concurrent=50)
        assert config.max_concurrent == 50

        # Invalid values - too low
        with pytest.raises(ValidationError):
            CrawlerConfig(max_concurrent=0)

        # Invalid values - too high
        with pytest.raises(ValidationError):
            CrawlerConfig(max_concurrent=51)

    def test_depth_validation(self):
        """Test that depth must be within valid range."""
        # Valid values
        config = CrawlerConfig(max_depth=1)
        assert config.max_depth == 1

        config = CrawlerConfig(max_depth=10)
        assert config.max_depth == 10

        # Invalid values - too low
        with pytest.raises(ValidationError):
            CrawlerConfig(max_depth=0)

        # Invalid values - too high
        with pytest.raises(ValidationError):
            CrawlerConfig(max_depth=11)


class TestParserConfig:
    """Test the ParserConfig model."""

    def test_default_values(self):
        """Test default values for ParserConfig."""
        config = ParserConfig()
        assert config.title_selector == "//title"
        assert config.content_selectors == ["//main", "//article", "//body"]
        assert config.fallback_to_body is True
        assert isinstance(config.markdown_config, HtmlToMarkdownConfig)

    def test_custom_values(self):
        """Test ParserConfig with custom values."""
        config = ParserConfig(
            title_selector="//h1",
            content_selectors=['//div[@id="main"]', "//article"],
            fallback_to_body=False,
        )
        assert config.title_selector == "//h1"
        assert config.content_selectors == ['//div[@id="main"]', "//article"]
        assert config.fallback_to_body is False

    def test_get_content_selector(self):
        """Test the get_content_selector method."""
        from lxml import html as lxml_html

        # Create a test config
        config = ParserConfig(
            content_selectors=[
                '//div[@id="main"]',
                '//div[@class="content"]',
                "//article",
            ],
        )

        # Create a test HTML tree
        html_content = """
        <html>
            <body>
                <div class="content">Content here</div>
                <article>Article content</article>
            </body>
        </html>
        """
        tree = lxml_html.fromstring(html_content)

        # Test first selector not found, second matches
        element = config.get_content_selector(tree)
        assert element is not None
        assert element.text == "Content here"

        # Test when first selector matches
        html_content = """
        <html>
            <body>
                <div id="main">Main content</div>
                <div class="content">Secondary content</div>
            </body>
        </html>
        """
        tree = lxml_html.fromstring(html_content)
        element = config.get_content_selector(tree)
        assert element is not None
        assert element.text == "Main content"

        # Test when no selectors match
        html_content = """
        <html>
            <body>
                <div class="other">Other content</div>
            </body>
        </html>
        """
        tree = lxml_html.fromstring(html_content)
        element = config.get_content_selector(tree)
        assert element is None


class TestSiteConfig:
    """Test the SiteConfig model."""

    def test_default_values(self):
        """Test default values for SiteConfig."""
        config = SiteConfig(
            base_url=HttpUrl("https://example.com"),
        )
        assert str(config.base_url) == "https://example.com/"
        assert config.description is None
        assert isinstance(config.parser_config, ParserConfig)
        assert isinstance(config.crawler_config, CrawlerConfig)

    def test_custom_values(self):
        """Test SiteConfig with custom values."""
        parser_config = ParserConfig(
            title_selector="//h1",
            content_selectors=['//div[@id="main"]'],
            fallback_to_body=False,
        )
        crawler_config = CrawlerConfig(
            delay_between_requests=2.0,
            max_concurrent=3,
        )

        config = SiteConfig(
            base_url=HttpUrl("https://example.com"),
            description="Test site",
            parser_config=parser_config,
            crawler_config=crawler_config,
        )

        assert str(config.base_url) == "https://example.com/"
        assert config.description == "Test site"
        assert config.parser_config.title_selector == "//h1"
        assert config.crawler_config.delay_between_requests == 2.0

    def test_base_dir_property(self):
        """Test the base_dir property."""
        config = SiteConfig(base_url=HttpUrl("https://example.com"))
        assert config.base_dir == "example.com"

        config = SiteConfig(base_url=HttpUrl("https://subdomain.example.com:8080"))
        assert config.base_dir == "subdomain.example.com"

    def test_invalid_base_url(self):
        """Test invalid base URLs."""
        # Now validation happens at initialization time with Pydantic HttpUrl
        with pytest.raises(ValidationError, match=r"Input should be a valid URL"):
            SiteConfig(base_url="not-a-url")  # type: ignore[arg-type]

        with pytest.raises(
            ValidationError, match=r"URL scheme should be 'http' or 'https'"
        ):
            SiteConfig(base_url="ftp://example.com")  # type: ignore[arg-type]

    def test_get_content_selector(self):
        """Test the get_content_selector method delegation."""
        from lxml import html as lxml_html

        # Create a test config with parser config
        parser_config = ParserConfig(
            content_selectors=[
                '//div[@id="main"]',
                '//div[@class="content"]',
                "//article",
            ],
        )
        config = SiteConfig(
            base_url=HttpUrl("https://example.com"),
            parser_config=parser_config,
        )

        # Create a test HTML tree
        html_content = """
        <html>
            <body>
                <div class="content">Content here</div>
                <article>Article content</article>
            </body>
        </html>
        """
        tree = lxml_html.fromstring(html_content)

        # Test first selector not found, second matches
        element = config.get_content_selector(tree)
        assert element is not None
        assert element.text == "Content here"

        # Test when first selector matches
        html_content = """
        <html>
            <body>
                <div id="main">Main content</div>
                <div class="content">Secondary content</div>
            </body>
        </html>
        """
        tree = lxml_html.fromstring(html_content)
        element = config.get_content_selector(tree)
        assert element is not None
        assert element.text == "Main content"

        # Test when no selectors match
        html_content = """
        <html>
            <body>
                <div class="other">Other content</div>
            </body>
        </html>
        """
        tree = lxml_html.fromstring(html_content)
        element = config.get_content_selector(tree)
        assert element is None


class TestHtmlToMarkdownConfig:
    """Test the HtmlToMarkdownConfig model."""

    def test_default_values(self):
        """Test default values."""
        config = HtmlToMarkdownConfig()
        assert config.ignore_links is False
        assert config.body_width == 0
        assert config.protect_links is True
        assert config.unicode_snob is True
        assert config.ignore_images is False
        assert config.ignore_tables is False

    def test_custom_values(self):
        """Test custom values."""
        config = HtmlToMarkdownConfig(
            ignore_links=True,
            body_width=80,
            protect_links=False,
            unicode_snob=False,
        )
        assert config.ignore_links is True
        assert config.body_width == 80
        assert config.protect_links is False
        assert config.unicode_snob is False


class TestParserConfigRegistry:
    """Test the ParserConfigRegistry model."""

    def test_model_validation(self):
        """Test model validation."""
        # Valid config with all required fields using new structure
        config_data = {
            "sites": {
                "test": {
                    "base_url": "https://example.com",
                    "parser_config": {
                        "content_selectors": ["//div"],
                    },
                },
            },
        }
        registry = ParserConfigRegistry.model_validate(config_data)
        assert "test" in registry.sites
        assert str(registry.sites["test"].base_url) == "https://example.com/"

        # Invalid config (missing required fields)
        with pytest.raises(ValidationError):
            ParserConfigRegistry.model_validate(
                {
                    "sites": {
                        "test": {"site_name": "test"},
                    },
                },
            )
