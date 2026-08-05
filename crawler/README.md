# Tapio crawler

This service owns source-site configuration and produces Markdown documents with `source_url` frontmatter. It does not access the vector store or serve user requests.

Run `uv sync`. Crawl4AI launches Playwright with the installed stable Google
Chrome channel, so install Google Chrome through your operating system before
starting a crawl; no Crawl4AI browser download is required.

The crawler and ingestion service exchange files through one shared content
directory. Locally this defaults to the repository's `content/` directory; in
deployment, mount the same directory into both services and set
`TAPIO_CONTENT_DIR` to its mount path.

## URL discovery and the manifest

`discover` builds a site's URL inventory and records it in a durable,
SQLite-backed manifest. Run this first for a site before `crawl` - rendering
reads only from the manifest, it does not discover URLs on its own:

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
writes Markdown - that's `crawl`'s job.

## Rendering: manifest-driven, resumable collection

`crawl` renders every manifest record that is due, into
`{TAPIO_CONTENT_DIR}/{site}/parsed/` Markdown:

```bash
uv run tapio-crawler crawl migri
```

A record is due on its first render, when its source's `discovery.trust_lastmod`
is `true` and the sitemap `lastmod` is newer than the last render, when it was
last rendered under an older extractor version, or once
`refresh.unchanged_audit_days` (default 90) has elapsed since its last check.
`--force` ignores that schedule and re-renders every eligible record.
`--max-urls` (default 5000) caps how many records one run processes;
`--batch-size` (default 500) is the manifest page size used while selecting
them. Progress is saved to the manifest after each record completes, so a
stopped run resumes from where it left off on the next invocation rather than
starting over.

Each saved document includes `title`, `source_url`, `canonical_url`,
`content_hash`, `language`, `extractor_version`, and `crawl_timestamp` YAML
frontmatter. Artifacts are keyed by `canonical_url`, not the URL as
discovered, so redirects and tracking-parameter variants of the same page
share one file.

Crawl4AI stores its persistent HTTP cache in `{TAPIO_CONTENT_DIR}/.crawl4ai/`
and uses conditional freshness checks (`ETag`/`Last-Modified`) before
re-rendering a page whose scheduled check finds it unchanged. Mount `content/`
as a persistent volume in deployment, or set `CRAWL4_AI_BASE_DIRECTORY` to
another persistent location.
