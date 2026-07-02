import time

import httpx


def start_crawl(
    account_id: str,
    api_token: str,
    url: str,
    depth: int = 2,
    limit: int = 100,
    render: bool = True,
    source: str = "all",
) -> str:
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

    response = httpx.post(endpoint, json=payload, headers=headers)
    response.raise_for_status()

    data = response.json()
    job_id = data["result"]

    return job_id


def wait_for_crawl(account_id: str, job_id: str, api_token: str) -> dict:
    max_attempts = 60
    delay_seconds = 5

    for _ in range(max_attempts):
        endpoint = (
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}"
            f"/browser-rendering/crawl/{job_id}?limit=1"
        )

        headers = {
            "Authorization": f"Bearer {api_token}",
        }

        response = httpx.get(endpoint, headers=headers)
        response.raise_for_status()

        data = response.json()
        status = data["result"]["status"]

        if status != "running":
            return data["result"]

        time.sleep(delay_seconds)

    raise TimeoutError("Crawl job did not complete within timeout")


def crawl_site(
    account_id: str,
    api_token: str,
    url: str,
    depth: int = 2,
    limit: int = 100,
    render: bool = True,
    source: str = "all",
) -> dict:
    job_id = start_crawl(
        account_id=account_id,
        api_token=api_token,
        url=url,
        depth=depth,
        limit=limit,
        render=render,
        source=source,
    )

    result = wait_for_crawl(
        account_id=account_id,
        job_id=job_id,
        api_token=api_token,
    )

    return result