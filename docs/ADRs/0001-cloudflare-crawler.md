# ADR 0001: Replace bespoke crawler and parser with Cloudflare Browser Rendering /crawl endpoint

## Status

Superseded by [0003](0003-crawl4ai-crawler.md)

## Date

2026-03-12

## Context

Tapio includes a custom-built async web crawler (`BaseCrawler` in `tapio/crawler/crawler.py`) that uses httpx and BeautifulSoup to fetch HTML pages, follow links to a configurable depth, manage concurrency via asyncio semaphores, and save results to disk. A separate `CrawlerRunner` (`tapio/crawler/runner.py`) orchestrates crawl execution, and a `Parser` (`tapio/parser/parser.py`) converts the saved HTML to Markdown using XPath selectors and html2text.

Together, these two stages require us to maintain:

- Async HTTP fetching with configurable timeouts and redirects
- Recursive link discovery, extraction, and domain filtering
- Depth-limited traversal with visited-URL deduplication
- Concurrency control (semaphore-based throttling)
- Rate limiting (configurable delay between requests)
- HTML file storage with URL-to-filepath mapping
- Content-type filtering
- Site-specific XPath content selectors (`ParserConfig`)
- HTML-to-Markdown conversion configuration (`HtmlToMarkdownConfig`)
- URL reverse-lookup from `url_mappings.json`
- YAML frontmatter generation

This is a significant amount of low-level infrastructure that diverts effort from higher-value work: document vectorization, RAG orchestration, multi-agent workflows, and user-facing features.

Cloudflare announced the Browser Rendering `/crawl` endpoint (open beta, March 2026) which provides all of this functionality — and more — via a single REST API call. The endpoint supports headless browser rendering, returns content in HTML/Markdown/JSON formats, handles sitemap and link discovery, supports incremental crawling, and respects robots.txt by default.

Our project crawls 5 Finnish government websites (migri, te_palvelut, kela, vero, dvv) to build a RAG knowledge base. The crawling needs are straightforward and well within the capabilities of the Cloudflare endpoint.

## Decision

Replace the bespoke `BaseCrawler`, `CrawlerRunner`, and `Parser` with a new implementation that wraps the Cloudflare Browser Rendering `/crawl` REST API. Cloudflare provides both crawling and Markdown conversion, eliminating two entire pipeline stages.

### What changes

1. **Remove** `BaseCrawler` class (`tapio/crawler/crawler.py`) — the entire custom crawling logic
2. **Remove** `Parser` class (`tapio/parser/parser.py`) — XPath extraction, HTML-to-Markdown conversion, frontmatter generation
3. **Remove** `ParserConfig` and `HtmlToMarkdownConfig` from `tapio/config/config_models.py`
4. **Remove** the `parse` CLI command from `tapio/cli.py`
5. **Rewrite** `CrawlerRunner` (`tapio/crawler/runner.py`) as a Cloudflare `/crawl` API client with:
   - Job initiation (POST)
   - Async polling for completion (GET with `?limit=1`)
   - Paginated result retrieval (GET with `cursor`)
   - Graceful handling of all terminal statuses
   - Saving Markdown files with YAML frontmatter containing the canonical source URL
6. **Update** `CrawlerConfig` model (`tapio/config/config_models.py`) to reflect Cloudflare parameters:
   - Remove: `delay_between_requests`, `max_concurrent` (handled by Cloudflare)
   - Keep: `max_depth` (maps to `depth`)
   - Add: `limit`, `render`, `source`, `formats`, `options.includePatterns`, `options.excludePatterns`, `maxAge`, `crawlPurposes`
7. **Update** site configurations (`tapio/config/site_configs.yaml`):
   - Remove all `parser_config` sections
   - Add Cloudflare-appropriate crawler defaults
8. **Update** the `crawl` CLI command (`tapio/cli.py`) for the async polling workflow
9. **Authenticate** via environment variables: `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`
10. **Remove** unused dependencies: BeautifulSoup, lxml, html2text

### What stays the same

- CLI interface for the `crawl` command (same command name and basic structure; flags will change to reflect the updated `CrawlerConfig` — flags for removed fields such as `--delay-between-requests` and `--max-concurrent` are dropped, replaced by new Cloudflare-based parameters such as `--limit`, `--render`, `--source`, and `--formats`)
- Site configuration structure (`base_url`, `description`)
- Downstream pipeline: vectorize → RAG app
- Markdown output saved to `content/{site}/parsed/` with YAML frontmatter

### Content Signals declaration

The `/crawl` endpoint respects [Content Signals](https://developers.cloudflare.com/robots-txt/content-signals/) directives published in a target site's `robots.txt`. The request accepts a `crawlPurposes` parameter (default: `["search", "ai-input", "ai-train"]`) declaring the intended use of crawled content; if a site's `Content-Signal` directive disallows any *declared* purpose, the request is rejected with a 400 error.

Tapio's use — retrieving chunked, vectorized content at query time to ground LLM-generated answers — matches Cloudflare's definition of **`ai-input`** ("retrieval augmented generation, grounding, or other real-time taking of content for generative AI"), not `search` (which covers only returning links and short excerpts, explicitly excluding AI-synthesized answers). All crawl requests should therefore declare:

```json
"crawlPurposes": ["ai-input"]
```

Declaring only the purpose actually in use is both more accurate and reduces the chance of an unnecessary rejection on sites that restrict `search` or `ai-train` but permit `ai-input`.

### Source URL requirement

Each saved Markdown file must include the canonical source URL in its YAML frontmatter, sourced from the Cloudflare response `metadata.url` field. This is essential for the RAG pipeline to cite original sources and ground answers with verifiable references:

```yaml
---
title: "Page Title"
source_url: "https://migri.fi/en/residence-permit"
crawl_timestamp: "2026-03-12T10:30:00Z"
---
```

## Consequences

### Positive

- **Less code to maintain** — Removes ~500 lines of crawling and parsing logic (link following, concurrency, rate limiting, HTML storage, XPath extraction, HTML-to-Markdown conversion, frontmatter generation)
- **Eliminates site-specific parser configuration** — No more maintaining XPath selectors (`ParserConfig`) and html2text settings (`HtmlToMarkdownConfig`) per site
- **Better crawling capabilities** — Headless browser rendering for JS-heavy sites, sitemap discovery, incremental crawling, pattern-based URL filtering
- **robots.txt compliance by default** — The Cloudflare crawler identifies itself as a bot and respects directives automatically
- **Markdown output with metadata** — Cloudflare returns Markdown directly along with URL and title metadata, providing the canonical source URL needed for RAG grounding
- **Caching and incremental crawls** — `maxAge` and `modifiedSince` parameters reduce redundant crawling
- **Focus on higher-value work** — Frees engineering effort for document vectorization, RAG orchestration, multi-agent workflows, and user-facing features

### Negative

- **External service dependency** — Crawling now depends on Cloudflare's API availability and account limits
- **API token management** — Requires a Cloudflare account and API token with Browser Rendering permissions
- **Cost** — `render: true` crawls consume headless browser time (billed per Cloudflare pricing). `render: false` is free during beta but will be billed later
- **Less control** — Cannot customize HTTP request headers, cookies, or retry logic as granularly as with our own client (though the API does support `setExtraHTTPHeaders`, `authenticate`, and cookie options)
- **Async polling** — Crawl jobs are asynchronous; the CLI must poll for completion rather than stream results in real-time
- **Free plan limits** — Workers Free plan is capped at 10 minutes of browser time per day

### Risks

- **Beta status** — The `/crawl` endpoint is in open beta. API surface may change
- **Bot protection** — Target sites using Cloudflare Bot Management or WAF may block the crawler. This is the same risk our current crawler faces, but worth noting. **Confirmed 2026-07-25**: `migri.fi` returns HTTP 403 ("Pääsy estetty / Förbjuden / Forbidden") from Valtori (the Finnish government's shared IT provider) regardless of `crawlPurposes`, ruling out a Content Signals rejection and confirming a WAF-level block. Since Valtori fronts multiple Finnish government sites, the other target sites (`te_palvelut`, `kela`, `vero`, `dvv`) should each be tested before committing further to this approach
- **Full-page vs. targeted content** — Cloudflare returns full-page Markdown rather than targeted content areas (XPath selectors). For RAG, full-page content is generally acceptable and may actually provide better context. If noise is an issue, Cloudflare's `includePatterns`/`excludePatterns` can scope URLs, and downstream chunking/embedding can handle content relevance

## Crawl test results (2026-07-25)

All five target sites (plus `finntegrate.org` as a non-target smoke test) were crawled with `render: true`, `formats: ["markdown"]`, `crawlPurposes: ["ai-input"]`, `limit: 1` against their front page, to validate reachability before further investment in this ADR.

| Site | URL tested | Result | Notes |
| --- | --- | --- | --- |
| finntegrate.org | `https://finntegrate.org/` | ✅ 200, completed in ~0.3 browser-seconds | Smoke test, not a pipeline target |
| migri | `https://migri.fi/` | ❌ 403 Forbidden | Blocked by Valtori's WAF ("Pääsy estetty / Förbjuden / Forbidden"). Confirmed this is not a Content Signals rejection — identical result with `crawlPurposes` narrowed to `["ai-input"]` |
| te_palvelut (old) | `https://toimistot.te-palvelut.fi/` | ❌ errored | No HTTP status returned, 0 browser-seconds used — domain appears defunct. TE Services' online office has moved to `tyomarkkinatori.fi` |
| tyomarkkinatori | `https://tyomarkkinatori.fi/` | ✅ 200, completed | Successor to `te_palvelut`; `site_configs.yaml` renamed accordingly |
| kela | `https://www.kela.fi/` | ✅ 200, completed (~2.6 browser-seconds) | Redirected to `/henkiloasiakkaat` |
| vero | `https://www.vero.fi/en/` | ✅ 200, completed | Redirected to `/en/individuals/` |
| dvv | `https://dvv.fi/` | ⚠️ stuck | Job stayed `queued` (0 browser-seconds used) for ~14 minutes with no terminal status. No `429`/rate-limit response headers observed at any point — likely a silent free-tier concurrency/queue limitation rather than a target-site block, since this job was submitted alongside four others in quick succession. Needs a retry in isolation to confirm |

Ad-hoc output for each successful crawl was saved to `crawl/<site>/index.md` (a scratch location for this test, not the `content/{site}/parsed/` pipeline output described above).

### Implementation notes from testing

- **Malformed JSON responses**: the beta `/crawl` API returns Markdown containing literal unescaped control characters and backslash-escaped Markdown syntax (e.g. `kela\_fpa`) that make the overall response invalid JSON. Both `jq` and Python's `json.loads` — even with `strict=False` — fail on these responses. The `CrawlerRunner` rewrite needs a lenient parser (e.g. pre-processing to double any backslash not followed by a valid JSON escape character before parsing with `strict=False`) rather than relying on strict JSON parsing.
- **Concurrency**: firing multiple crawl jobs concurrently on the free tier appears able to starve individual jobs in an invisible queue — no error, no rate-limit header, just an indefinite `queued` status (see `dvv` above). `CrawlerRunner` should default to sequential or low-concurrency job submission across sites rather than firing all site crawls in parallel.

## Alternatives considered

### 1. Keep the bespoke crawler and improve it

Continue maintaining `BaseCrawler` and `Parser` with incremental improvements (sitemap support, better JS handling via Playwright, etc.). Rejected because this increases our maintenance burden for functionality that Cloudflare provides out of the box, and keeps us focused on low-level infrastructure instead of higher-value features.

### 2. Use Scrapy or another crawling framework

Replace our custom code with an established Python crawling framework. Rejected because this still requires us to maintain crawling infrastructure, handle JS rendering separately, and manage concurrency — the same problems Cloudflare solves with less code.

### 3. Use Cloudflare Workers with Browser Rendering bindings

Deploy a Cloudflare Worker that uses the Browser Rendering bindings directly for more control. Rejected for this phase — the REST API `/crawl` endpoint is simpler to integrate and sufficient for our needs. Could revisit if we need fine-grained control later.

## References

- [Cloudflare /crawl endpoint documentation](https://developers.cloudflare.com/browser-rendering/rest-api/crawl-endpoint/)
- [Browser Rendering REST API setup](https://developers.cloudflare.com/browser-rendering/rest-api/)
- [Cloudflare Blog: Crawl entire websites with a single API call (March 10, 2026)](https://developers.cloudflare.com/changelog/post/2026-03-10-br-crawl-endpoint/)
