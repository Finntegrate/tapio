# Tapio crawler

This service owns source-site configuration and produces Markdown documents with `source_url` frontmatter. It does not access the vector store or serve user requests.

Run `uv sync`. Crawl4AI launches Playwright with the installed stable Google
Chrome channel, so install Google Chrome through your operating system before
starting a crawl; no Crawl4AI browser download is required.

The crawler and ingestion service exchange files through one shared content
directory. Locally this defaults to the repository's `content/` directory; in
deployment, mount the same directory into both services and set
`TAPIO_CONTENT_DIR` to its mount path.

Collect a configured site directly into `{TAPIO_CONTENT_DIR}/{site}/parsed/`
Markdown:

```bash
uv run tapio-crawler crawl migri
```

Use `--depth 0` for a single-page smoke test. Each saved document includes
`title`, `source_url`, and `crawl_timestamp` YAML frontmatter for ingestion.

## Polite re-crawls

Each site is crawled at most once every 30 days by default
(`recrawl_interval_hours: 720`), with a per-site override in
`tapio_crawler/config/site_configs.yaml`. A successful crawl records its time
in `{TAPIO_CONTENT_DIR}/{site}/crawl_state.json`; use `--force` only when an immediate
refresh is needed.

When a site is due, Crawl4AI stores its persistent cache in
`{TAPIO_CONTENT_DIR}/.crawl4ai/` and uses conditional freshness checks (`ETag`/
`Last-Modified`) before rendering a cached page again. Mount `content/` as a
persistent volume in deployment, or set `CRAWL4_AI_BASE_DIRECTORY` to another
persistent location.

## URL discovery and the manifest

`discover` builds a site's URL inventory - separately from crawling and
rendering - and records it in a durable, SQLite-backed manifest:

```bash
uv run tapio-crawler discover migri
```

For a source with a sitemap (`discovery.source: sitemap` in
`site_configs.yaml`), this fetches the sitemap(s) directly, following one
level of sitemap-index nesting and preserving each URL's `lastmod`. For a
source with no sitemap, set `discovery.source: none` and
`gap_crawl.enabled: true` with `seed_urls`; discovery then runs a bounded BFS
crawl instead. Every discovered URL is scored against the site's `scope`
config (`allowed_domains`, `include_url_patterns`, `exclude_url_patterns`) and
upserted into the manifest with its eligibility.

The manifest lives at `{TAPIO_CONTENT_DIR}/manifest.db` by default; override
its path with `TAPIO_MANIFEST_PATH`. A discovery run never renders pages or
writes Markdown - that remains `crawl`'s job.
