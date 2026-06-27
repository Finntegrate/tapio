"""Test cases for the async BaseCrawler implementation."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import httpx
import pytest
from bs4 import BeautifulSoup
from pydantic import HttpUrl

from tapio.config.config_models import CrawlerConfig, SiteConfig
from tapio.crawler.crawler import BaseCrawler


def create_test_site_config(
    base_url: str = "https://example.com",
    depth: int = 1,
    delay_between_requests: float = 0.0,
    max_concurrent: int = 5,
) -> SiteConfig:
    """Create a test SiteConfig for testing."""
    return SiteConfig(
        base_url=HttpUrl(base_url),
        crawler_config=CrawlerConfig(
            max_depth=depth,
            delay_between_requests=delay_between_requests,
            max_concurrent=max_concurrent,
        ),
    )


class TestBaseCrawler:
    """Test cases for BaseCrawler class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.output_dir = "test_crawler_output"
        os.makedirs(self.output_dir, exist_ok=True)

    def teardown_method(self):
        """Clean up test fixtures."""
        import shutil

        if os.path.exists(self.output_dir):
            shutil.rmtree(self.output_dir)

    def test_init(self):
        """Test crawler initialization."""
        site_config = create_test_site_config(
            base_url="https://example.com",
            depth=2,
        )
        crawler = BaseCrawler("test_site", site_config)

        assert crawler.start_urls == ["https://example.com/"]  # URLs are normalized with trailing slash
        assert crawler.max_depth == 2
        assert crawler.allowed_domains == ["example.com"]

        # Test with different URL
        site_config2 = create_test_site_config(
            base_url="https://test.com",
            depth=1,
        )
        crawler2 = BaseCrawler("test_site2", site_config2)
        assert crawler2.start_urls == ["https://test.com/"]  # URLs are normalized with trailing slash
        assert crawler2.allowed_domains == ["test.com"]

    def test_get_file_path_from_url(self):
        """Test URL to file path conversion."""
        site_config = create_test_site_config("https://example.com")
        crawler = BaseCrawler("test_site", site_config)

        # Test basic URL
        path = crawler._get_file_path_from_url("https://example.com")
        expected = os.path.join(crawler.output_dir, "example.com", "index.html")
        assert path == expected

        # Test URL with path
        path = crawler._get_file_path_from_url("https://example.com/page")
        expected = os.path.join(crawler.output_dir, "example.com", "page.html")
        assert path == expected

        # Test URL with query parameters
        path = crawler._get_file_path_from_url("https://example.com/page?param=value")
        expected_start = os.path.join(crawler.output_dir, "example.com", "page_param_value")
        assert path.startswith(expected_start)
        assert path.endswith(".html")

    def test_get_file_path_from_url_with_trailing_slash(self):
        """Test URL to file path conversion with trailing slash."""
        site_config = create_test_site_config("https://example.com")
        crawler = BaseCrawler("test_site", site_config)

        path = crawler._get_file_path_from_url("https://example.com/path/")
        expected = os.path.join(crawler.output_dir, "example.com", "path.html")
        assert path == expected

    def test_save_html_content(self):
        """Test saving HTML content to file."""
        site_config = create_test_site_config("https://example.com")
        crawler = BaseCrawler("test_site", site_config)

        url = "https://example.com/test"
        html_content = "<html><body><h1>Test Page</h1></body></html>"
        crawler._save_html_content(url, html_content)

        expected_path = crawler._get_file_path_from_url(url)
        assert os.path.exists(expected_path)

        with open(expected_path, encoding="utf-8") as f:
            saved_content = f.read()
            assert saved_content == html_content

    def test_is_allowed_domain(self):
        """Test domain filtering."""
        site_config = create_test_site_config("https://example.com")
        crawler = BaseCrawler("test_site", site_config)

        assert crawler._is_allowed_domain("https://example.com/page")
        assert not crawler._is_allowed_domain("https://test.com/page")
        assert not crawler._is_allowed_domain("https://other.com/page")

    def test_extract_links(self):
        """Test extracting links from BeautifulSoup."""
        site_config = create_test_site_config("https://example.com")
        crawler = BaseCrawler("test_site", site_config)

        html = """
        <html>
            <body>
                <a href="/page1">Page 1</a>
                <a href="https://example.com/page2">Page 2</a>
                <a href="https://other.com/page3">Page 3</a>
                <a href="#fragment">Fragment</a>
                <a href="mailto:test@example.com">Email</a>
            </body>
        </html>
        """

        soup = BeautifulSoup(html, "lxml")
        base_url = "https://example.com"

        links = crawler._extract_links(soup, base_url)

        expected_links = ["https://example.com/page1", "https://example.com/page2"]

        assert sorted(links) == sorted(expected_links)

    def test_save_url_mappings(self):
        """Test saving URL mappings to a JSON file."""
        site_config = create_test_site_config("https://example.com")
        crawler = BaseCrawler("test_site", site_config)

        crawler.url_mappings = {
            "example.com/page1.html": {
                "url": "https://example.com/page1",
                "timestamp": "2023-01-01T00:00:00",
                "content_type": "text/html",
            },
        }

        with patch("pathlib.Path.open", mock_open()) as mock_file:
            crawler._save_url_mappings()
            expected_path = os.path.join(crawler.output_dir, "url_mappings.json")
            assert crawler.mapping_file == expected_path
            mock_file.assert_called_once_with("w", encoding="utf-8")

    def test_save_url_mappings_exception(self):
        """Test handling exceptions when saving URL mappings."""
        site_config = create_test_site_config("https://example.com")
        crawler = BaseCrawler("test_site", site_config)

        crawler.url_mappings = {
            "test.html": {
                "url": "https://example.com/test",
                "timestamp": "2023-01-01T00:00:00",
                "content_type": "text/html",
            },
        }

        with (
            patch("pathlib.Path.open", side_effect=Exception("Test error")),
            patch("tapio.crawler.crawler.logger.exception") as mock_log,
        ):
            crawler._save_url_mappings()
            mock_log.assert_called_once_with("Error saving URL mappings")

    @pytest.mark.asyncio
    async def test_crawl_url_success(self):
        """Test successful crawling of a single URL."""
        site_config = create_test_site_config(
            base_url="https://example.com",
            depth=1,  # Minimum depth is 1
            max_concurrent=1,
        )
        crawler = BaseCrawler("test_site", site_config)
        # Override max_depth to 0 for this test to prevent following links
        crawler.max_depth = 0

        mock_response = MagicMock()
        mock_response.text = "<html><body><h1>Test</h1><a href='/page2'>Link</a></body></html>"
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        # Mock the semaphore to avoid async context issues
        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock(return_value=None)
        mock_semaphore.__aexit__ = AsyncMock(return_value=None)
        crawler._semaphore = mock_semaphore

        with patch.object(crawler, "_save_html_content", return_value="/fake/path.html"):
            results = []
            await crawler._crawl_url(mock_client, "https://example.com/", 0, results)

            mock_client.get.assert_called_once_with("https://example.com/")

            assert len(results) == 1
            result = results[0]
            assert result["url"] == "https://example.com/"
            assert result["depth"] == 0
            assert "Test" in result["html"]

    @pytest.mark.asyncio
    async def test_crawl_url_http_error(self):
        """Test handling HTTP errors during crawling."""
        site_config = create_test_site_config("https://example.com")
        crawler = BaseCrawler("test_site", site_config)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "404 Not Found",
                request=MagicMock(),
                response=MagicMock(status_code=404),
            ),
        )

        # Mock the semaphore to avoid async context issues
        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock(return_value=None)
        mock_semaphore.__aexit__ = AsyncMock(return_value=None)
        crawler._semaphore = mock_semaphore

        results = []
        with patch("tapio.crawler.crawler.logger.warning") as mock_log:
            await crawler._crawl_url(mock_client, "https://example.com/404", 0, results)

            mock_log.assert_called()
            assert len(results) == 0

    @pytest.mark.asyncio
    async def test_crawl_url_non_html_content(self):
        """Test handling non-HTML content."""
        site_config = create_test_site_config("https://example.com")
        crawler = BaseCrawler("test_site", site_config)

        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        # Mock the semaphore to avoid async context issues
        mock_semaphore = AsyncMock()
        mock_semaphore.__aenter__ = AsyncMock(return_value=None)
        mock_semaphore.__aexit__ = AsyncMock(return_value=None)
        crawler._semaphore = mock_semaphore

        results = []
        await crawler._crawl_url(mock_client, "https://example.com/doc.pdf", 0, results)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_crawl_url_semaphore_deadlock_prevention(self):
        """Test that semaphore is properly released before processing child links to prevent deadlock."""
        site_config = create_test_site_config(
            base_url="https://example.com",
            depth=2,
            max_concurrent=2,  # Low limit to test semaphore behavior
        )
        crawler = BaseCrawler("test_site", site_config)

        # Track semaphore acquire/release calls using patches
        semaphore_calls: list[str] = []

        # Mock the semaphore with proper tracking
        original_semaphore = crawler.semaphore

        class MockSemaphore:
            def __init__(self, original: asyncio.Semaphore):
                self.original = original
                self._call_count = 0

            async def __aenter__(self):
                self._call_count += 1
                semaphore_calls.append(f"acquire_{self._call_count}")
                return await self.original.__aenter__()

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                semaphore_calls.append(f"release_{self._call_count}")
                return await self.original.__aexit__(exc_type, exc_val, exc_tb)

        # Patch the semaphore property
        with patch.object(type(crawler), "semaphore", MockSemaphore(original_semaphore)):
            # Mock responses for parent and child pages
            parent_html = """
            <html>
                <body>
                    <h1>Parent Page</h1>
                    <a href="/child1">Child 1</a>
                    <a href="/child2">Child 2</a>
                </body>
            </html>
            """

            child_html = """
            <html>
                <body>
                    <h1>Child Page</h1>
                    <a href="/grandchild">Grandchild</a>
                </body>
            </html>
            """

            def mock_get_side_effect(url):
                mock_response = MagicMock()
                mock_response.headers = {"content-type": "text/html; charset=utf-8"}
                mock_response.raise_for_status = MagicMock()

                if url == "https://example.com":
                    mock_response.text = parent_html
                else:
                    mock_response.text = child_html

                return mock_response

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=mock_get_side_effect)

            with patch.object(crawler, "_save_html_content", return_value="/fake/path.html"):
                results: list = []
                await crawler._crawl_url(mock_client, "https://example.com", 0, results)

                # Verify that semaphore was acquired and released properly
                assert len(semaphore_calls) > 0
                # Should have acquire/release pairs for each URL processed
                acquire_count = len([call for call in semaphore_calls if call.startswith("acquire")])
                release_count = len([call for call in semaphore_calls if call.startswith("release")])
                assert acquire_count == release_count, "Semaphore acquire/release mismatch"

                # Should have processed multiple URLs (parent + children)
                assert len(results) > 1, "Should have crawled child links"

    @pytest.mark.asyncio
    async def test_crawl_concurrent_requests_respect_semaphore_limit(self):
        """Test that concurrent requests don't exceed the semaphore limit."""
        max_concurrent = 2
        site_config = create_test_site_config(
            base_url="https://example.com",
            depth=1,
            max_concurrent=max_concurrent,
        )
        crawler = BaseCrawler("test_site", site_config)

        # Track concurrent requests
        concurrent_requests: list[str] = []
        max_concurrent_seen = 0

        async def mock_get_with_tracking(url):
            concurrent_requests.append(url)
            nonlocal max_concurrent_seen
            max_concurrent_seen = max(max_concurrent_seen, len(concurrent_requests))

            # Simulate request duration
            await asyncio.sleep(0.1)

            mock_response = MagicMock()
            mock_response.text = f"""
            <html>
                <body>
                    <h1>Page {url}</h1>
                    <a href="/child1">Child 1</a>
                    <a href="/child2">Child 2</a>
                </body>
            </html>
            """
            mock_response.headers = {"content-type": "text/html; charset=utf-8"}
            mock_response.raise_for_status = MagicMock()

            concurrent_requests.remove(url)
            return mock_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=mock_get_with_tracking)

        with patch.object(crawler, "_save_html_content", return_value="/fake/path.html"):
            results: list = []
            await crawler._crawl_url(mock_client, "https://example.com", 0, results)

            # Verify that we never exceeded the semaphore limit
            assert max_concurrent_seen <= max_concurrent, (
                f"Exceeded max concurrent limit: {max_concurrent_seen} > {max_concurrent}"
            )

    @pytest.mark.asyncio
    async def test_crawl_multi_level_depth_without_deadlock(self):
        """Test crawling multiple levels deep without causing deadlock."""
        site_config = create_test_site_config(
            base_url="https://example.com",
            depth=2,  # Test 2 levels deep (reduced from 3)
            max_concurrent=2,
        )
        crawler = BaseCrawler("test_site", site_config)

        # Mock different HTML for each level with fewer links to avoid explosion
        def create_mock_response(url, depth):
            mock_response = MagicMock()
            mock_response.headers = {"content-type": "text/html; charset=utf-8"}
            mock_response.raise_for_status = MagicMock()

            if depth == 0:  # Root page
                mock_response.text = """
                <html>
                    <body>
                        <h1>Root Page</h1>
                        <a href="/page1">Page 1</a>
                    </body>
                </html>
                """
            elif depth == 1:  # Level 1 pages
                mock_response.text = """
                <html>
                    <body>
                        <h1>Level 1 Page</h1>
                        <a href="/page2">Page 2</a>
                    </body>
                </html>
                """
            else:  # Level 2 and deeper - no more links
                mock_response.text = """
                <html>
                    <body>
                        <h1>Leaf Page</h1>
                    </body>
                </html>
                """
            return mock_response

        # Track which URLs are requested
        requested_urls: list[str] = []

        def mock_get_side_effect(url):
            requested_urls.append(url)

            # Determine depth based on URL pattern
            if url == "https://example.com":
                depth = 0
            elif url == "https://example.com/page1":
                depth = 1
            elif url == "https://example.com/page2":
                depth = 2
            else:
                depth = 3  # Should not reach this with depth=2

            return create_mock_response(url, depth)

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=mock_get_side_effect)

        with patch.object(crawler, "_save_html_content", return_value="/fake/path.html"):
            results: list = []

            # This should complete without hanging (no deadlock)
            await asyncio.wait_for(
                crawler._crawl_url(mock_client, "https://example.com", 0, results),
                timeout=5.0,  # Should complete well within 5 seconds if no deadlock
            )

            # Verify we crawled multiple levels
            depths_crawled = {result["depth"] for result in results}
            assert len(depths_crawled) > 1, "Should have crawled multiple depth levels"
            assert max(depths_crawled) <= 2, "Should not exceed max depth"
            assert len(results) >= 2, "Should have crawled multiple pages"

            # Verify specific URLs were requested
            expected_urls = ["https://example.com", "https://example.com/page1", "https://example.com/page2"]
            for expected_url in expected_urls:
                assert expected_url in requested_urls, f"Expected URL {expected_url} was not requested"

    @pytest.mark.asyncio
    async def test_crawl_links_processed_outside_semaphore_context(self):
        """Test that child links are processed outside the semaphore context to prevent deadlock."""
        site_config = create_test_site_config(
            base_url="https://example.com",
            depth=1,
            max_concurrent=1,  # Force sequential processing
        )
        crawler = BaseCrawler("test_site", site_config)

        # Track when HTTP requests are made vs when child links are processed
        processing_events: list[str] = []

        # Mock the HTTP client to track request timing
        async def mock_get_with_tracking(url):
            processing_events.append(f"http_request_start_{url}")

            mock_response = MagicMock()
            mock_response.headers = {"content-type": "text/html; charset=utf-8"}
            mock_response.raise_for_status = MagicMock()

            if url == "https://example.com":
                mock_response.text = """
                <html>
                    <body>
                        <h1>Parent Page</h1>
                        <a href="/child1">Child 1</a>
                    </body>
                </html>
                """
            else:
                mock_response.text = "<html><body><h1>Child</h1></body></html>"

            processing_events.append(f"http_request_end_{url}")
            return mock_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=mock_get_with_tracking)

        with patch.object(crawler, "_save_html_content", return_value="/fake/path.html"):
            results: list = []
            await crawler._crawl_url(mock_client, "https://example.com", 0, results)

            # Verify the request processing order
            parent_end_idx = next(
                i for i, event in enumerate(processing_events) if event == "http_request_end_https://example.com"
            )
            child_start_idx = next(
                (
                    i
                    for i, event in enumerate(processing_events)
                    if event.startswith("http_request_start_https://example.com/child")
                ),
                -1,
            )

            # Child request should start AFTER parent request completes
            # This indicates semaphore was released before processing child links
            if child_start_idx != -1:
                assert child_start_idx > parent_end_idx, (
                    "Child links should be processed after parent request completes"
                )

    @pytest.mark.asyncio
    async def test_crawl_full_integration(self):
        """Test the full crawl method with mocked HTTP client."""
        site_config = create_test_site_config(
            base_url="https://example.com",
            depth=1,
            max_concurrent=1,
        )
        crawler = BaseCrawler("test_site", site_config)

        html_content = """
        <html>
            <body>
                <h1>Main Page</h1>
                <a href="/page1">Page 1</a>
            </body>
        </html>
        """

        mock_response = MagicMock()
        mock_response.text = html_content
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        # Mock the async context manager
        mock_client_context = AsyncMock()
        mock_client_context.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_context.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("httpx.AsyncClient", return_value=mock_client_context),
            patch.object(crawler, "_save_html_content"),
        ):
            # Mock the _semaphore attribute to avoid async context issues
            mock_semaphore = AsyncMock()
            mock_semaphore.__aenter__ = AsyncMock(return_value=None)
            mock_semaphore.__aexit__ = AsyncMock(return_value=None)
            crawler._semaphore = mock_semaphore

            results = await crawler.crawl()

            assert len(results) > 0
            assert results[0]["url"] == "https://example.com/"  # URLs are normalized

    def test_get_file_path_from_url_path_traversal_protection(self):
        """Test that path traversal attacks are prevented."""
        site_config = create_test_site_config("https://example.com")
        crawler = BaseCrawler("test_site", site_config)

        # Test path traversal attempts that should be blocked
        malicious_urls = [
            "https://example.com/../../../etc/passwd",
            "https://example.com/normal/../../../sensitive",
            "https://example.com/path/../../../../../../etc/hosts",
        ]

        for malicious_url in malicious_urls:
            with pytest.raises(ValueError, match="Invalid URL results in path outside output directory"):
                crawler._get_file_path_from_url(malicious_url)

        # Test that URL-encoded path separators are treated as literal characters (not path traversal)
        safe_encoded_url = "https://example.com/..%2F..%2F..%2Fetc%2Fpasswd"
        result = crawler._get_file_path_from_url(safe_encoded_url)
        # This should succeed because %2F is not decoded to / by urlparse
        expected = os.path.join(crawler.output_dir, "example.com", "..%2F..%2F..%2Fetc%2Fpasswd.html")
        assert result == expected
