# Tapio crawler

This service owns source-site configuration and produces Markdown documents with `source_url` frontmatter. It does not access the vector store or serve user requests.

Run `uv sync`. Crawl4AI launches Playwright with the installed stable Google
Chrome channel, so install Google Chrome through your operating system before
starting a crawl; no Crawl4AI browser download is required.

The crawler and ingestion service exchange files through one shared content
directory. Locally this defaults to the repository's `content/` directory; in
deployment, mount the same directory into both services and set
`TAPIO_CONTENT_DIR` to its mount path.

## Running several sites at once, and operator controls

`run-all` runs discovery then rendering for every configured site (or the sites
you name) as independent concurrent jobs. Each job has its own manifest
connection, its own politeness delay, and its own progress line:

```bash
uv run tapio-crawler run-all                          # every configured site
uv run tapio-crawler run-all migri kela               # a subset
uv run tapio-crawler run-all --max-concurrent-sites 2 # cap simultaneous browsers
```

`retry` re-renders records whose last fetch failed, without a new `discover` +
`crawl` cycle. It ignores retry backoff and the per-URL retry cap, because you
are asking for the attempt now. Add `--include-inactive` to also retry
`inactive_candidate` records:

```bash
uv run tapio-crawler retry migri --include-inactive
```

While either command runs, signals steer every job. In-flight requests are
never interrupted, so the manifest stays consistent and resumable:

| Signal              | Effect                                                         |
| ------------------- | -------------------------------------------------------------- |
| `SIGUSR1`           | Pause: no new requests start.                                  |
| `SIGUSR2`           | Resume.                                                        |
| `SIGINT`/`SIGTERM`  | Cancel gracefully (exit code 130); a second `SIGINT` forces it. |

Each site renders in its own Crawl4AI browser, which costs memory and CPU.
Before defaulting to all sites at once on a constrained host (CI, a small
deployment box), measure it: run with `--report-resources` at
`--max-concurrent-sites 1`, `2`, ... and compare the reported peak RSS/CPU of
the process tree.

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
