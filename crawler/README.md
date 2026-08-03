# Tapio crawler

This service owns source-site configuration and produces Markdown documents with `source_url` frontmatter. It does not access the vector store or serve user requests.

Run `uv sync`, then install Crawl4AI's Playwright/Patchright browser binaries once:

```bash
uv run crawl4ai-setup
```

Collect a configured site directly into `content/{site}/parsed/` Markdown:

```bash
uv run tapio-crawler crawl migri
```

Use `--depth 0` for a single-page smoke test. Each saved document includes
`title`, `source_url`, and `crawl_timestamp` YAML frontmatter for ingestion.

## Polite re-crawls

Each site is crawled at most once every 30 days by default
(`recrawl_interval_hours: 720`), with a per-site override in
`tapio_crawler/config/site_configs.yaml`. A successful crawl records its time
in `content/{site}/crawl_state.json`; use `--force` only when an immediate
refresh is needed.

When a site is due, Crawl4AI stores its persistent cache in
`content/.crawl4ai/` and uses conditional freshness checks (`ETag`/
`Last-Modified`) before rendering a cached page again. Mount `content/` as a
persistent volume in deployment, or set `CRAWL4_AI_BASE_DIRECTORY` to another
persistent location.
