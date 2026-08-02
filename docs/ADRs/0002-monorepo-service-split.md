# ADR 0002: Split the repository into independent crawler, ingest, and app projects

## Status

Proposed

## Date

2026-07-25

## Context

Tapio currently lives as a single `uv` project rooted at the repository root: one `pyproject.toml`, one `uv.lock`, one dependency tree, and one CLI (`tapio/cli.py`) covering four distinct concerns — crawl, parse, vectorize, and serve the chat app (`tapio/app.py`).

This bundling was tenable while the pipeline was simple, but it creates real friction as the project evolves:

- **Dependency pollution** — Adopting a headless-browser crawler (see [ADR 0003](0003-crawl4ai-crawler.md)) means the same dependency tree that ships the user-facing chat app now also pulls in Playwright/Patchright and their multi-hundred-megabyte Chromium binaries, even though the app itself never renders a page.
- **Coupled deploys and release cadence** — The crawler ideally runs on a schedule (e.g. nightly/weekly via CI) against government websites. The ingestion/vectorization step runs whenever new crawled content lands. The chat app is a long-lived service. These are three different operational shapes forced to share one deploy artifact today.
- **Unclear ownership boundaries** — `tapio/crawler`, `tapio/parser`, and `tapio/vectorstore` are implementation details of a data pipeline, not concerns of a user-facing RAG assistant. Mixing them in the same package makes it harder to reason about what the "app" actually is.
- **Blocks independent experimentation** — There's a stated interest in evolving the Tapio app's front end independently (e.g. a Rocket.Chat integration, a bespoke channels-based UI) without needing to touch or re-test crawler/ingestion code, and vice versa.

A recent fail-fast experiment (2026-07-25, see [ADR 0003](0003-crawl4ai-crawler.md)) also validated that a different crawling engine (Crawl4AI) outperforms the Cloudflare-based approach proposed in [ADR 0001](0001-cloudflare-crawler.md) on our actual target sites. Swapping crawler engines is exactly the kind of change that should be possible without touching the app or the ingestion pipeline — reinforcing the case for separating these concerns now rather than later.

## Decision

We will restructure the repository into a monorepo containing three independently-managed root-level `uv` projects, each with its own `pyproject.toml` and `uv.lock`:

- **`crawler/`** — Sole responsibility: produce Markdown output (with YAML frontmatter carrying the canonical `source_url`) from the configured government/informational sites. Owns the crawling engine and its dependencies. Technology choice covered in [ADR 0003](0003-crawl4ai-crawler.md).
- **`ingest/`** — Sole responsibility: ingest the Markdown (and PDF) output produced by `crawler/` into a vector database. Owns the chunking/embedding/vector-store dependencies. Technology choice covered in [ADR 0004](0004-cocoindex-ingestion.md).
- **`tapio/`** — The user-facing application: agents, orchestration (LangChain/LangGraph), and exposed interfaces (chat UI, API, MCP). Reads from the vector database populated by `ingest/` via a direct database connection (see [ADR 0004](0004-cocoindex-ingestion.md)). No longer owns crawling, parsing, or vectorization code.

What moves where:

- `pyproject.toml`, `uv.lock`, `mypy.ini`, `pytest.ini`, `pyrefly.toml` move from the repository root into `tapio/`, becoming that project's own root.
- `tapio/crawler/` and `tapio/parser/` are removed from the `tapio` project; their replacement lives in the new `crawler/` project.
- `tapio/vectorstore/` is removed from the `tapio` project; its replacement lives in the new `ingest/` project. `tapio/` keeps only the retrieval-side code (a database client/retriever), not the ingestion pipeline.
- `tapio/config/site_configs.yaml` moves to `crawler/` (it configures crawling, not the app).
- The `crawl`, `parse`, and `vectorize` CLI commands are removed from `tapio/cli.py`; `crawler/` and `ingest/` get their own minimal CLIs or scheduled entry points.

What stays shared at the repository root:

- `docs/ADRs/`, `README.md`, `CONTRIBUTING.md`, `WORKFLOW.md`, `LICENSE`.
- `mise.toml`, extended to define tasks scoped per project (e.g. `mise run tapio:test`, `mise run crawler:crawl`) rather than one global task set.
- CI (`.github/workflows/`), restructured so each project's checks (lint, type-check, test) run independently — and, ideally, only when that project's files change.
- A shared local-dev `docker-compose.yml` providing the Postgres/pgvector instance used by `ingest/` and `tapio/` (see [ADR 0004](0004-cocoindex-ingestion.md)).

## Consequences

### Positive

- **Isolated dependency trees** — The chat app's deploy artifact no longer carries headless-browser binaries; the crawler's deploy artifact doesn't carry LangChain/Gradio.
- **Independent release and operational cadence** — Each project can be deployed, scheduled, and scaled according to its own shape (scheduled job vs. long-lived service).
- **Clear single-responsibility boundaries** — `crawler/` produces Markdown, `ingest/` produces vectors, `tapio/` produces answers. Each is testable and replaceable in isolation, as already demonstrated by the crawler engine swap in ADR 0003.
- **Enables independent experimentation on the app** — New front ends or integrations (Rocket.Chat, bespoke channel UIs, additional API consumers) can be built against `tapio/` without any risk to or dependency on the crawling/ingestion code.
- **Faster, more targeted CI** — Per-project checks mean a documentation-only or app-only change doesn't need to wait on crawler or ingestion test suites.

### Negative

- **More repository ceremony** — Three lockfiles instead of one; `mise.toml` and CI configuration grow more complex to correctly scope tasks per project.
- **Cross-project contract changes require coordinated PRs** — Changing the Markdown/frontmatter format `crawler/` emits requires a matching change in `ingest/`'s parsing, potentially across two separate PRs/reviews.
- **No shared virtualenv** — Common dependencies (e.g. `pydantic`, `pyyaml`) are duplicated across the three lockfiles rather than resolved once.
- **Local dev setup gets more involved** — Contributors now need to know about (and potentially run) three separate projects plus a shared Postgres instance, rather than one `uv sync`.

### Risks

- **Contract drift** — Without an explicit, tested schema for the Markdown+frontmatter handoff between `crawler/` and `ingest/`, the two projects can silently drift out of sync.
- **Tooling misconfiguration** — Incorrectly scoped `mise` tasks or CI triggers could run the wrong project's tests, or skip needed ones, especially during the transition period.
- **Onboarding friction** — New contributors need to understand the monorepo layout and which project a given change belongs in; this ADR and updated `CONTRIBUTING.md` documentation need to make that obvious.

## Alternatives considered

### 1. Keep a single project, add the crawler dependencies as an optional dependency group

Use `uv`'s optional dependency groups (`tapio[crawler]`) to keep everything in one `pyproject.toml`. Rejected because it doesn't solve the deploy-artifact coupling (the app's Docker image would still need to conditionally exclude the group, which `uv` doesn't make significantly easier than a separate project) and does nothing for independent release cadence or CI scoping.

### 2. Split into fully separate repositories

Give `crawler`, `ingest`, and `tapio` each their own GitHub repository. Rejected for now because it adds cross-repo versioning and dependency overhead (e.g. pinning which `crawler` release an `ingest` deployment expects) and fragments issues, PRs, and ADRs across repos. A monorepo keeps planning and architecture history centralized while still achieving dependency isolation through separate `uv` projects.

### 3. Use `uv` workspaces instead of fully independent projects

`uv` supports workspaces, which share a single lockfile across multiple projects while still allowing per-project dependency declarations. This is a plausible middle ground and could reduce some of the "Negative" consequences above (shared resolution of common dependencies). It was not chosen initially because it still ties the three projects to a single lockfile resolution, which partially undercuts the independent-release goal — but this is worth revisiting if the duplicated-lockfile overhead proves painful in practice.

## References

- [ADR 0001: Replace bespoke crawler and parser with Cloudflare Browser Rendering /crawl endpoint](0001-cloudflare-crawler.md) (superseded by ADR 0003)
- [ADR 0003: Adopt Crawl4AI for the crawler service](0003-crawl4ai-crawler.md)
- [ADR 0004: Adopt CocoIndex and Postgres/pgvector for the ingestion service](0004-cocoindex-ingestion.md)
- [uv workspaces documentation](https://docs.astral.sh/uv/concepts/projects/workspaces/)
