"""Tests for BaseCrawler — the Cloudflare-backed crawler."""

from unittest.mock import patch

import pytest
from pydantic import HttpUrl

from tapio.config.config_models import CrawlerConfig, SiteConfig
from tapio.crawler.crawler import BaseCrawler


def make_test_site_config(
    base_url: str = "https://example.com",
    max_depth: int = 1,
    limit: int = 10,
    render: bool = True,
    source: str = "all",
) -> SiteConfig:
    """Build a minimal SiteConfig for tests."""
    return SiteConfig(
        base_url=HttpUrl(base_url),
        crawler_config=CrawlerConfig(
            max_depth=max_depth,
            limit=limit,
            render=render,
            source=source,
        ),
    )


def make_cloudflare_record(url: str, status: str, markdown: str = "", title: str = "") -> dict:
    """Build a record dict as Cloudflare would return it."""
    return {
        "url": url,
        "status": status,
        "markdown": markdown,
        "metadata": {"title": title, "status": 200, "url": url},
    }


class TestBaseCrawler:
    """Behavior of BaseCrawler with Cloudflare backend."""

    def test_init_reads_env_vars_and_config(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "test-account")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "test-token")
        monkeypatch.chdir(tmp_path)

        site_config = make_test_site_config(
            base_url="https://x.com",
            max_depth=2,
            limit=50,
            render=False,
            source="sitemaps",
        )

        crawler = BaseCrawler("test-site", site_config)

        assert crawler.site_name == "test-site"
        assert crawler.account_id == "test-account"
        assert crawler.api_token == "test-token"
        assert crawler.max_depth == 2
        assert crawler.limit == 50
        assert crawler.render is False
        assert crawler.source == "sitemaps"

    def test_init_raises_when_credentials_missing(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        monkeypatch.chdir(tmp_path)

        # Also block .env loading so tests don't accidentally pick up real creds
        with (
            patch("tapio.crawler.crawler.load_dotenv"),
            pytest.raises(ValueError, match="CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN"),
        ):
            BaseCrawler("test-site", make_test_site_config())

    def test_filter_completed_keeps_only_completed_records(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "b")
        monkeypatch.chdir(tmp_path)

        crawler = BaseCrawler("t", make_test_site_config())

        records = [
            make_cloudflare_record("a", "completed"),
            make_cloudflare_record("b", "errored"),
            make_cloudflare_record("c", "queued"),
            make_cloudflare_record("d", "completed"),
            make_cloudflare_record("e", "skipped"),
        ]

        result = crawler._filter_completed(records)

        assert [r["url"] for r in result] == ["a", "d"]

    def test_get_file_path_builds_md_paths(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "b")
        monkeypatch.chdir(tmp_path)

        crawler = BaseCrawler("t", make_test_site_config())

        p_root = crawler._get_file_path_from_url("https://example.com/")
        p_deep = crawler._get_file_path_from_url("https://example.com/en/about")
        p_query = crawler._get_file_path_from_url("https://example.com/page?x=1&y=2")

        assert p_root.endswith(("example.com\\index.md", "example.com/index.md"))
        assert p_deep.endswith(("en\\about.md", "en/about.md"))
        assert "page_x_1_y_2.md" in p_query

    def test_get_file_path_blocks_path_traversal(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "b")
        monkeypatch.chdir(tmp_path)

        crawler = BaseCrawler("t", make_test_site_config())

        with pytest.raises(ValueError, match="outside output directory"):
            crawler._get_file_path_from_url("https://example.com/../../../etc/passwd")

    def test_crawl_processes_completed_records_and_ignores_others(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "b")
        monkeypatch.chdir(tmp_path)

        fake_cloudflare_response = {
            "status": "completed",
            "records": [
                make_cloudflare_record("https://x.com/a", "completed", "# A", "Page A"),
                make_cloudflare_record("https://x.com/b", "errored", "", ""),
                make_cloudflare_record("https://x.com/c", "completed", "# C", "Page C"),
            ],
        }

        with patch("tapio.crawler.crawler.crawl_site", return_value=fake_cloudflare_response):
            crawler = BaseCrawler("t", make_test_site_config())
            results = crawler.crawl()

        assert len(results) == 2
        assert results[0]["url"] == "https://x.com/a"
        assert results[0]["markdown"] == "# A"
        assert results[0]["title"] == "Page A"
        assert results[1]["url"] == "https://x.com/c"
        assert results[1]["title"] == "Page C"

    def test_crawl_returns_empty_when_all_records_errored(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "b")
        monkeypatch.chdir(tmp_path)

        fake_cloudflare_response = {
            "status": "completed",
            "records": [
                make_cloudflare_record("https://x.com/a", "errored"),
                make_cloudflare_record("https://x.com/b", "errored"),
            ],
        }

        with patch("tapio.crawler.crawler.crawl_site", return_value=fake_cloudflare_response):
            crawler = BaseCrawler("t", make_test_site_config())
            results = crawler.crawl()

        assert results == []

    def test_save_url_mappings_logs_on_write_failure(self, monkeypatch, tmp_path, caplog):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
        monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "b")
        monkeypatch.chdir(tmp_path)

        crawler = BaseCrawler("t", make_test_site_config())

        with patch("pathlib.Path.open", side_effect=OSError("disk full")):
            # Should not raise
            crawler._save_url_mappings()
