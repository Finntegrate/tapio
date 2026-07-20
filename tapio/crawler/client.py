"""HTTP client for the Cloudflare Browser Rendering /crawl API."""

import time

import httpx


def start_crawl(  # noqa: PLR0913
    account_id: str,
    api_token: str,
    url: str,
    depth: int = 2,
    limit: int = 100,
    render: bool = True,
    source: str = "all",
) -> str:
    """Start a crawl job and return its job id."""
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/browser-rendering/crawl"

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "url": url,
        "depth": depth,
        "limit": limit,
        "formats": ["markdown"],
        "render": render,
        "source": source,
    }

    response = httpx.post(endpoint, json=payload, headers=headers, timeout=30)
    response.raise_for_status()

    return response.json()["result"]


def wait_for_crawl(account_id: str, job_id: str, api_token: str) -> dict:
    """Poll the crawl job until it finishes , then return the full paginated result."""
    max_attempts = 100
    delay_seconds = 5
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/browser-rendering/crawl/{job_id}"

    headers = {"Authorization": f"Bearer {api_token}"}

    for _ in range(max_attempts):
        # limit = 1 keeps polling responses lightweight
        response = httpx.get(endpoint, headers=headers, params={"limit": 1}, timeout=30)
        response.raise_for_status()
        status = response.json()["result"]["status"]
        if status != "running":
            break
        time.sleep(delay_seconds)
    else:
        msg = "Crawl job did not complete within timeout"
        raise TimeoutError(msg)

    # fetch full results, following cursor pagination (Responses over 10 mb are paged)
    records: list[dict] = []
    params: dict = {}
    while True:
        response = httpx.get(endpoint, headers=headers, params=params, timeout=120)
        response.raise_for_status()
        result = response.json()["result"]
        records.extend(result.get("records", []))
        cursor = result.get("cursor")
        if not cursor:
            break
        params = {"cursor": cursor}
    result["records"] = records
    return result


def crawl_site(  # noqa: PLR0913
    account_id: str,
    api_token: str,
    url: str,
    depth: int = 2,
    limit: int = 100,
    render: bool = True,
    source: str = "all",
) -> dict:
    """Run a full crawl: start the job , wait for it , and return the result."""
    job_id = start_crawl(
        account_id=account_id,
        api_token=api_token,
        url=url,
        depth=depth,
        limit=limit,
        render=render,
        source=source,
    )

    return wait_for_crawl(
        account_id=account_id,
        job_id=job_id,
        api_token=api_token,
    )
