"""Tests for the Cloudflare /crawl API client."""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from tapio.crawler.client import crawl_site, start_crawl, wait_for_crawl


def make_fake_response(status_code: int, json_body: dict) -> MagicMock:
    """Build a MagicMock that behaves like an httpx.Response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = json_body
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"Client error {status_code}",
            request=MagicMock(),
            response=response,
        )
    else:
        response.raise_for_status.return_value = None
    return response


def test_start_crawl_posts_correct_payload_and_returns_job_id():
    fake = make_fake_response(200, {"success": True, "result": "fake-job-id"})

    with patch("tapio.crawler.client.httpx.post", return_value=fake) as mock_post:
        job_id = start_crawl(
            account_id="acc123",
            api_token="tok456",
            url="https://example.com",
            depth=2,
            limit=50,
            render=True,
            source="all",
        )

    assert job_id == "fake-job-id"

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args

    assert args[0] == "https://api.cloudflare.com/client/v4/accounts/acc123/browser-rendering/crawl"

    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer tok456"
    assert headers["Content-Type"] == "application/json"

    payload = kwargs["json"]
    assert payload["url"] == "https://example.com"
    assert payload["depth"] == 2
    assert payload["limit"] == 50
    assert payload["render"] is True
    assert payload["source"] == "all"
    assert payload["formats"] == ["markdown"]


def test_start_crawl_raises_on_http_error():
    fake = make_fake_response(401, {"success": False, "errors": [{"message": "Invalid token"}]})

    with patch("tapio.crawler.client.httpx.post", return_value=fake):
        with pytest.raises(httpx.HTTPStatusError):
            start_crawl(account_id="acc", api_token="bad", url="https://example.com")


def test_wait_for_crawl_returns_immediately_on_completed():
    fake = make_fake_response(200, {"success": True, "result": {"status": "completed", "records": []}})

    with patch("tapio.crawler.client.httpx.get", return_value=fake) as mock_get:
        with patch("tapio.crawler.client.time.sleep") as mock_sleep:
            result = wait_for_crawl(account_id="acc", job_id="job-1", api_token="tok")

    assert result["status"] == "completed"
    assert mock_get.call_count == 1
    assert mock_sleep.call_count == 0


def test_wait_for_crawl_polls_until_completed():
    running = make_fake_response(200, {"success": True, "result": {"status": "running", "records": []}})
    completed = make_fake_response(200, {"success": True, "result": {"status": "completed", "records": []}})

    with patch("tapio.crawler.client.httpx.get", side_effect=[running, running, completed]) as mock_get:
        with patch("tapio.crawler.client.time.sleep") as mock_sleep:
            result = wait_for_crawl(account_id="acc", job_id="job-1", api_token="tok")

    assert result["status"] == "completed"
    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2


def test_wait_for_crawl_raises_timeout():
    running = make_fake_response(200, {"success": True, "result": {"status": "running", "records": []}})

    with patch("tapio.crawler.client.httpx.get", return_value=running):
        with patch("tapio.crawler.client.time.sleep"):
            with pytest.raises(TimeoutError):
                wait_for_crawl(account_id="acc", job_id="job-1", api_token="tok")


def test_crawl_site_chains_start_and_wait():
    fake_result = {"status": "completed", "records": [{"url": "x"}]}

    with patch("tapio.crawler.client.start_crawl", return_value="chained-job-id") as mock_start:
        with patch("tapio.crawler.client.wait_for_crawl", return_value=fake_result) as mock_wait:
            returned = crawl_site(
                account_id="acc",
                api_token="tok",
                url="https://x.com",
                depth=1,
                limit=10,
                render=True,
                source="all",
            )

    assert returned is fake_result

    mock_start.assert_called_once_with(
        account_id="acc",
        api_token="tok",
        url="https://x.com",
        depth=1,
        limit=10,
        render=True,
        source="all",
    )
    mock_wait.assert_called_once_with(
        account_id="acc",
        job_id="chained-job-id",
        api_token="tok",
    )