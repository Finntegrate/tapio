# ADR 0003: Adopt Crawl4AI for the crawler service

## Status

Accepted

## Date

2026-07-25

## Context

[ADR 0001](0001-cloudflare-crawler.md) proposed replacing Tapio's bespoke `httpx` + BeautifulSoup crawler with Cloudflare's Browser Rendering `/crawl` REST API, reasoning that an external managed service would eliminate the maintenance burden of running our own headless-browser crawling infrastructure.

On 2026-07-25 we tested that proposal empirically against all five sites configured in `site_configs.yaml`, plus a smoke test against `finntegrate.org` (full results recorded in ADR 0001's "Crawl test results" section):

| Site | Cloudflare `/crawl` result |
| --- | --- |
| finntegrate.org | ✅ 200, completed in ~0.3s |
| migri | ❌ 403 Forbidden — blocked by Valtori's WAF, independent of `crawlPurposes` declaration |
| te_palvelut (old domain) | ❌ errored — domain defunct, unrelated to Cloudflare |
| tyomarkkinatori | ✅ 200 |
| kela | ✅ 200 |
| vero | ✅ 200 |
| dvv | ⚠️ stuck `queued` for ~14 minutes with 0 browser-seconds used, never reached a terminal state |

Two of five actual target sites failed: `migri.fi` — the Finnish Immigration Service, arguably the single most important source for Tapio's mission — was blocked outright, and `dvv.fi` failed silently with no error, rate-limit header, or diagnosable cause, only an indefinite queue stall plausibly caused by free-tier concurrency limits (see ADR 0001's "Implementation notes").

As a fail-fast comparison, we ran the same five front-page fetches locally using [Crawl4AI](https://github.com/unclecode/crawl4ai), an open-source, Playwright/Patchright-based headless-browser crawler, with default configuration (no site-specific tuning). All five succeeded:

| Site | Crawl4AI result | Time |
| --- | --- | --- |
| migri | ✅ 302, 67KB Markdown | 0.8s |
| tyomarkkinatori | ✅ 301, 54KB Markdown | 0.7s |
| kela | ✅ 307, 8KB Markdown | 1.0s |
| vero | ✅ 302, 15KB Markdown | 1.0s |
| dvv | ✅ 302, 71KB Markdown | 0.7s |

Notably, `migri.fi` — blocked at the WAF level when crawled via Cloudflare's shared infrastructure — was reachable when crawled directly from a local browser instance, and `dvv.fi` completed in under a second with no queueing. The `migri.fi` output was manually verified to be genuine page content (correct title, full navigation structure), not a block page.

This is a single, front-page-only, small-sample test — it does not validate full-depth crawling, sitemap discovery, or behavior under sustained crawl volume — but it directly contradicts ADR 0001's premise that offloading crawling to Cloudflare would be strictly less operational burden than running our own crawler.

## Decision

We will adopt Crawl4AI as the crawling engine, superseding ADR 0001's Cloudflare Browser Rendering `/crawl` proposal. This supersedes ADR 0001 in full; see [ADR 0001](0001-cloudflare-crawler.md) for the record of that decision and the test results that led to this reversal.

Crawl4AI is housed in the new root-level `crawler/` project ([ADR 0002](0002-monorepo-service-split.md)). Like the Cloudflare endpoint, Crawl4AI produces Markdown directly from a rendered page, so ADR 0001's original insight still holds: no separate HTML-to-Markdown parsing stage is needed. `tapio/parser` and its XPath-based `ParserConfig` remain removed, as ADR 0001 intended — just via a different underlying engine.

### What changes from ADR 0001's plan

- The `crawler/` project depends on `crawl4ai` and its Playwright/Patchright browser binaries (installed via `crawl4ai-setup`), not a Cloudflare API client.
- No Cloudflare account, API token, or `crawlPurposes` Content Signals declaration is needed.
- `CrawlerConfig` is redefined around Crawl4AI's parameters instead of the Cloudflare-specific fields ADR 0001 drafted (`limit`, `render`, `crawlPurposes`, `maxAge`, etc.) — `page_timeout`, a `RateLimiter`, a `SemaphoreDispatcher`/`MemoryAdaptiveDispatcher`, and a `BFSDeepCrawlStrategy`, each verified against the current config surface below ("Configuration parity with the current crawler").
- Output remains Markdown with YAML frontmatter carrying the canonical `source_url`, per ADR 0001's "Source URL requirement" — this contract is unchanged and is what `ingest/` ([ADR 0004](0004-cocoindex-ingestion.md)) consumes.

### Targeted content extraction

The current bespoke crawler avoids indexing navigation menus, repeated footers, and other site chrome through `ParserConfig`'s per-site XPath `content_selectors` (`tapio/config/site_configs.yaml`) — e.g. `//div[@id="main-content"]`, `//main[@role="main"]`, `//section[@id="content"]`, one hand-tuned set per site. ADR 0001 planned to drop this entirely, reasoning that "full-page content is generally acceptable" for RAG. The [ADR 0004 CocoIndex spike](0004-cocoindex-ingestion.md#spike-results-2026-07-25) showed that reasoning was too optimistic in practice: full-page Markdown produced weak, nav-link-dominated retrieval results.

We tested three extraction strategies against `migri.fi`'s front page (Crawl4AI supports all of these natively, no separate parser stage needed):

| Strategy | Config needed | Size |
| --- | --- | --- |
| Full page (current default) | none | 65,884 chars / 751 lines |
| `css_selector` targeting (mirrors old per-site XPath selectors) | per-site CSS selector | 7,252 chars / 72 lines (−89%) |
| `PruningContentFilter` (automatic content-density scoring) | none | 5,834 chars / 51 lines (−91%) |
| `excluded_tags=["nav","header","footer","form"]` + `PruningContentFilter` | one generic, site-independent config | 5,523 chars / 49 lines (−92%) |

Two findings from this test:

1. **Automatic filtering matched or beat hand-maintained per-site selectors, with no site-specific configuration at all.** `PruningContentFilter` scores DOM nodes by content density/link ratio and prunes low-value ones — it achieved a *better* reduction than replicating the old per-site `content_selectors` by hand. Combined with a small, generic `excluded_tags` list (not tuned per site), it did slightly better still.
2. **Even the best extraction still left mostly navigation links** for this specific page, because `migri.fi`'s front page *is*, structurally, a directory of links — there's little prose on a homepage to extract. This confirms the ADR 0004 spike's conclusion from the other direction: the fix for retrieval-quality noise is crawling into interior content pages, not just cleaner front-page extraction. Targeted extraction's real payoff will show on interior pages, which mix real body text with the same recurring nav/footer chrome.

We also tested `fallback_to_body` — the current `ParserConfig` field that falls back to the full `<body>` when none of its XPath `content_selectors` match, guarding against silently near-empty output if a site's markup changes. **Crawl4AI's `css_selector` has no equivalent fallback**: pointing it at a selector that matches nothing returned `success=True` with 1 character of markdown — not an error, just silently near-empty content. This is a real regression risk *if* we lean on per-site `css_selector` overrides, and it's a further point in favor of `PruningContentFilter` as the default: it scores content density across the whole page rather than requiring an exact selector match, so it degrades gracefully (worst case: more boilerplate included) instead of failing silently to near-nothing.

**Decision**: `crawler/` will use `excluded_tags` (a small, generic, site-independent list) plus `PruningContentFilter` as the default extraction strategy for every site, replacing the old per-site `ParserConfig.content_selectors` maintenance burden with a single, shared, automatic configuration. `CrawlerConfig` retains an optional per-site `css_selector`/`target_elements` override (mirroring the old XPath `content_selectors`) as an escape hatch for sites where automatic pruning performs poorly — but given the silent-near-empty failure mode above, any per-site override must be paired with a post-crawl sanity check (e.g. flag or reject results under some minimum length) rather than trusted blindly, and should be the exception, not the default for every site the way `ParserConfig` was.

### Configuration parity with the current crawler

The rest of `CrawlerConfig`/`ParserConfig` (`tapio/config/config_models.py`) was validated against Crawl4AI's API the same way — these settings exist today because of real experimentation (per-site rate limits, concurrency limits, depth limits), so the new crawler needs to either carry the same capability forward or make an explicit, informed call to drop it.

| Current field | Purpose | Crawl4AI equivalent | Verification |
| --- | --- | --- | --- |
| `delay_between_requests` (fixed `float`, e.g. 1.0–1.5s) | Politeness delay between requests | `RateLimiter(base_delay=(min, max), max_delay, max_retries, rate_limit_codes)` | Confirmed via API inspection. **Improvement**: a jittered delay *range* (less bot-like than a fixed sleep) plus automatic backoff/retry on rate-limit response codes (e.g. 429) — the current crawler has no backoff at all, just a fixed sleep regardless of server response. |
| `max_concurrent` (`asyncio.Semaphore`, 1–50) | Concurrency cap per site | `SemaphoreDispatcher(semaphore_count=N)` — direct equivalent; or `MemoryAdaptiveDispatcher` | Confirmed via API inspection. `SemaphoreDispatcher` is a like-for-like port. `MemoryAdaptiveDispatcher` (throttles by actual system memory pressure) is worth preferring in `crawler/`, since headless-browser concurrency is far more memory-sensitive than the current `httpx`-based crawler's lightweight requests. |
| `max_depth` (1–10) + `_is_allowed_domain` (manual domain check) | Depth-limited traversal, same-domain only | `BFSDeepCrawlStrategy(max_depth=N, include_external=False, max_pages=N)` | **Verified live** against `finntegrate.org`: crawled depth 0 → 1, correctly stayed in-domain, each result tagged with its `depth`. Also gains a `max_pages` safety cap (absent today — the current crawler has no total-page limit, only depth) and `BestFirstCrawlingStrategy`/`url_scorer` for prioritized crawling, neither available in the bespoke crawler. |
| `title_selector` (XPath, default `//title`) | Extract page title | `result.metadata["title"]`, automatic | **Verified live**: correct title (`"Etusivu \| Maahanmuuttovirasto"`) extracted with zero configuration. Simplification — no per-site override needed in practice. |
| `markdown_config.*` (`ignore_links`, `body_width`, `protect_links`, `unicode_snob`, `ignore_images`, `ignore_tables`) | HTML→Markdown formatting, mapped today to `html2text` options | `DefaultMarkdownGenerator(options={...})` | **Verified live** with the exact current field names and values. Crawl4AI vendors its own fork of `html2text` internally (`crawl4ai/html2text/`) — the option names are identical, so every site's existing `markdown_config` block ports over unchanged, field-for-field. |

Net result: every dimension of the current `CrawlerConfig`/`ParserConfig` has a verified Crawl4AI equivalent, and three of them (rate limiting, concurrency, depth) are strict upgrades — backoff-on-429, memory-aware concurrency, and a page-count safety cap the current crawler lacks entirely. The one regression to guard against is `fallback_to_body`'s silent-near-empty failure mode, addressed above by preferring automatic content filtering over per-site selectors.

## Consequences

### Positive

- **No external SaaS dependency** — Eliminates Cloudflare API availability, beta-API stability, and account/token management as operational concerns.
- **Not subject to an opaque queueing system** — The `dvv.fi` failure mode (indefinite silent queueing with no error signal) has no equivalent when crawling runs locally and synchronously.
- **Reached the most important target site** — `migri.fi`, blocked entirely under the Cloudflare approach, succeeded here.
- **Self-hosted, inspectable, no vendor lock-in** — Crawl4AI is open source; behavior can be debugged and patched directly rather than treated as a black box.
- **No incremental cost as crawl volume grows** — No per-render billing; cost is our own compute.
- **Cleaner content without per-site maintenance** — `excluded_tags` + `PruningContentFilter` cut boilerplate by ~92% on a test page with a single, site-independent configuration, beating the old per-site `ParserConfig.content_selectors` on the same metric while removing that per-site maintenance burden entirely (see "Targeted content extraction" above).
- **Rate limiting and concurrency control are strict upgrades, not just ports** — verified equivalents exist for every current `CrawlerConfig` field (see "Configuration parity" above), and three of them improve on today's behavior: `RateLimiter` adds jittered delays and automatic backoff on rate-limit response codes (the current crawler has no backoff at all), `MemoryAdaptiveDispatcher` throttles concurrency by actual memory pressure (relevant now that crawling means running real browser instances, not lightweight `httpx` requests), and `BFSDeepCrawlStrategy` adds a `max_pages` safety cap the bespoke crawler never had.

### Negative

- **We now own browser-binary management** — Playwright/Patchright downloads several hundred megabytes of Chromium binaries that must be installed and kept current in CI images and any deployment target.
- **We lose Cloudflare's bundled extras** — Sitemap discovery, `maxAge`-based incremental crawling, and automatic Content Signals (`robots.txt`) handling were included with the Cloudflare endpoint. Crawl4AI has some equivalent capabilities, but none have been validated in our testing yet — this needs a follow-up spike before we rely on them.
- **We still operate our own concurrency/rate-limiting infrastructure** — running full-depth, multi-page crawls at scale still means configuring and running `RateLimiter`/`SemaphoreDispatcher`/`BFSDeepCrawlStrategy` ourselves (the same concerns `BaseCrawler` handled, and that ADR 0001 hoped to offload entirely to Cloudflare). We are swapping which library provides headless-browser automation, not eliminating the need to operate one — though, per "Configuration parity" above, what we're now operating is more capable than what it replaces, not merely equivalent.

### Risks

- **Small sample size** — Only front-page, single-URL fetches were tested. Full-depth crawling, sitemap discovery, and incremental re-crawl behavior are unvalidated.
- **Direct-IP crawling may draw its own blocks over time** — `migri.fi` and `dvv.fi` succeeded when crawled directly from our infrastructure's IP/browser fingerprint rather than via Cloudflare's shared crawling IPs. This could reverse as crawl volume increases and government WAFs adapt; today's success is not a durable guarantee.
- **Browser binary maintenance becomes our responsibility** — Version drift between Crawl4AI, Playwright/Patchright, and the target sites' bot-detection heuristics needs ongoing attention, including keeping CI/deploy images in sync.
- **robots.txt / Content Signals compliance is no longer automatic** — Unlike Cloudflare's endpoint, Crawl4AI does not enforce Content Signals declarations for us; if we want to honor `ai-input`-only crawling (per ADR 0001's Content Signals decision), we need to implement or configure that ourselves.
- **Content extraction alone does not fix retrieval quality on front pages** — even the best-tested extraction strategy left mostly navigation links for `migri.fi`'s front page, because homepages are structurally link directories. `crawler/` needs to crawl into interior/content pages (depth > 0, sitemap- or link-driven) for `ingest/` to have substantive prose to index; this has not yet been implemented or tested.
- **`PruningContentFilter`'s default threshold is untuned** — the `threshold=0.48` used in testing is the library default, not validated against our target sites' actual markup patterns. It may need per-site or global tuning once tested against interior content pages rather than just front pages.
- **No automatic fallback when a per-site `css_selector` override matches nothing** — verified live: a non-matching `css_selector` returns `success=True` with near-empty markdown, not an error and not a fallback to full-page content (unlike the current `ParserConfig.fallback_to_body`). Any per-site override adopted in `crawler/` must be paired with a post-crawl minimum-length check, or a site markup change could silently degrade a crawl to near-empty output with no failure signal.

## Alternatives considered

### 1. Proceed with Cloudflare per ADR 0001

Rejected given the empirical 403 block on `migri.fi` and the unexplained `dvv.fi` queue stall — two of five target sites unreachable is a blocking outcome, not a minor rough edge.

### 2. Keep the original bespoke `httpx` + BeautifulSoup crawler

Rejected for the same reasons ADR 0001 gave: higher ongoing maintenance, no built-in Markdown conversion, and no headless rendering for JavaScript-heavy pages.

### 3. Use Cloudflare as a primary engine with Crawl4AI as a fallback for blocked sites

Rejected for now as unnecessary complexity — maintaining two crawling engines and a dispatch/fallback strategy is a larger maintenance surface than committing to one well-tested engine. Worth revisiting only if Crawl4AI itself proves unreliable at scale.

### 4. Carry over per-site XPath/CSS content selectors as the primary extraction strategy

Reimplement `ParserConfig.content_selectors` as per-site `css_selector`/`target_elements` values in the new `crawler/` project. Tested directly against `excluded_tags` + `PruningContentFilter` (see "Targeted content extraction" above) and rejected as the *default* — the automatic, site-independent approach matched or beat hand-tuned selectors on the one page tested, without the ongoing per-site maintenance burden ADR 0001 originally wanted to eliminate. Kept available as an optional per-site override for sites where automatic pruning underperforms.

## References

- [ADR 0001: Replace bespoke crawler and parser with Cloudflare Browser Rendering /crawl endpoint](0001-cloudflare-crawler.md) (superseded by this ADR)
- [ADR 0002: Split the repository into independent crawler, ingest, and app projects](0002-monorepo-service-split.md)
- [ADR 0004: Adopt CocoIndex and Postgres/pgvector for the ingestion service](0004-cocoindex-ingestion.md)
- [Crawl4AI GitHub repository](https://github.com/unclecode/crawl4ai)
- Crawl4AI fail-fast experiment results (2026-07-25), saved under `crawl4ai/<site>/index.md` during this test
- `tapio/config/config_models.py` and `tapio/config/site_configs.yaml` — current `CrawlerConfig`/`ParserConfig` schema, used as the baseline for the configuration-parity comparison
- Targeted content extraction comparison (2026-07-25): full page vs. `css_selector` vs. `PruningContentFilter` vs. `excluded_tags` + `PruningContentFilter`, tested against `migri.fi`
- Configuration parity verification (2026-07-25): `RateLimiter`, `SemaphoreDispatcher`/`MemoryAdaptiveDispatcher`, `BFSDeepCrawlStrategy` (live-tested against `finntegrate.org`), automatic title extraction, and `DefaultMarkdownGenerator(options=...)` vs. the current `html2text`-based `HtmlToMarkdownConfig`
