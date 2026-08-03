# ADR 0006: Retire Gradio, fold `tapio/` into `backend/`, adopt SvelteKit as the client

## Status

Accepted

## Date

2026-08-03

## Context

[ADR 0005](0005-multi-agent-chat-experience.md) explicitly named the Gradio prototype's mobile-first and accessibility limitations as a known negative, deferring the client decision to issue [#36](https://github.com/Finntegrate/tapio/issues/36). That evaluation happened: a FastAPI HTTP/SSE layer was scaffolded in `backend/` against the existing `tapio/` RAG and agent-routing orchestration (`RAGOrchestrator`, `AgentRouter`, the guide definitions), reusing it as a local editable dependency rather than porting it to TypeScript LangChain, and a SvelteKit frontend was scaffolded in `app/` (see the merged PR that added `app/`). Both proved out: the backend streams real routing/citation/token events end-to-end against Ollama and the populated `vectorstore/`.

With that validated, keeping `tapio/` as a separate project stopped making sense. It existed as its own `uv` project under [ADR 0002](0002-monorepo-service-split.md)'s three-way split (`crawler`/`ingest`/`tapio`) because the Gradio chat app was the single consumer of the RAG/agent logic. Now that `backend/` is the actual consumer — and the only one, since nothing else imports `tapio.*` outside `backend/` itself — routing the dependency through a separate package via `[tool.uv.sources]` added a layer of indirection (an extra lockfile, an editable path dependency, a `py.typed` marker to bridge mypy across the boundary) with no corresponding benefit. It also meant `backend/`'s dependency tree transitively carried Gradio, Torch-via-Gradio, and other UI-only packages it never used.

A migration audit (grep across the whole repo, cross-checked against actual runtime call sites) also found that `tapio/tapio/utils/` (`embedding_utils.py`, `text_utils.py`) and `tapio/tapio/models/document.py` were dead code: `RAGOrchestratorFactory` builds `HuggingFaceEmbeddings` directly rather than through `EmbeddingGenerator`, and no retrieval or service code imports `tapio.models.Document`. Their only callers were their own tests and their own `__init__.py` re-exports — vestiges of a pre-ADR-0002 layout, not code the query path depends on.

## Decision

We will delete the Gradio UI (`tapio/tapio/app.py`) and its launcher CLI (`tapio/tapio/cli.py`), move the RAG/agent-routing orchestration (`agents/`, `config/`, `prompts/`, `services/`, `retrieval.py`, `factories.py`) directly into `backend/tapio_backend/`, delete the dead `utils/`/`models/` code rather than migrating it, and delete the standalone `tapio/` project entirely. `backend/` becomes the single home for both the orchestration logic and the HTTP/SSE API that exposes it — matching what ADR 0002 already anticipated new front ends would build against.

The SvelteKit `app/` becomes the real, user-facing client, replicating what the Gradio prototype did (a shared conversation, visible guide identity and routing reason per turn, streaming text, source citations) by calling `backend/`'s `GET /agents` and `POST /chat/stream` endpoints directly from the browser, using the CORS support already built into `backend/`'s settings.

Every internal `from tapio.` import becomes `from tapio_backend.`; the `config` package absorbs the pre-existing `BackendSettings` module (renamed to `config/backend_settings.py`) to resolve the module/package name collision. `backend/pyproject.toml` drops `typer`, `gradio`, `langchain`, `langchain-community`, and `langchain-text-splitters` (only the deleted Gradio/CLI/dead-code paths used them) and gains `langchain-chroma`, `langchain-huggingface`, and `ollama` directly.

## Consequences

### Positive

- One project (`backend/`) instead of two, with one lockfile, no cross-project editable path dependency, and no `py.typed` bridging marker needed.
- `backend/`'s dependency tree drops Gradio, its transitive Torch pull, and other UI-only packages — confirmed via `uv lock` (Gradio, `gradio-client`, `hf-gradio`, `langchain`, `langchain-community`, `langchain-text-splitters`, and the `langgraph*` family all dropped out).
- Deleting confirmed-dead code (`utils/`, `models/document.py`) instead of migrating it keeps the merged package's surface area honest — everything in `backend/tapio_backend/` is now something the query path actually calls.
- Resolves the accessibility/mobile-first gap ADR 0005 flagged as a negative consequence of the Gradio prototype.

### Negative

- The old `tapio serve --model-name <model>` CLI flag has no equivalent in the FastAPI backend yet; model selection is currently fixed to `RAGConfig`'s defaults. Runtime configurability via `BackendSettings`-style env vars is a reasonable fast-follow, not addressed here.
- The SvelteKit chat UI ships as a first pass: guide picker and auto-routing are present, but `@mention`-style guide selection (which the backend router already supports) and broader end-to-end test coverage are deferred.
- `CONTRIBUTING.md`'s "Configuration System" section (referencing `config_manager.py`, `site_configs.yaml`, `DEFAULT_DIRS`) was already stale before this change and remains so — out of scope here, flagged separately.

### Risks

- Historical ADRs 0001–0004 reference `tapio/` internal paths (e.g. `tapio/crawler/crawler.py`) that predate even ADR 0002's split and are now further out of date. Left as-is per standard ADR convention (a record of decisions made, not a living document), aside from the superseded-note added to ADR 0002 below.
- Two test files' `mock.patch("tapio.services....")`-style string targets were easy to miss during the import-path rewrite (string literals aren't caught by an import-statement search) — worth double-checking test coverage stays green after any future refactor of this package for the same reason.

## Alternatives considered

### Keep `tapio/` as a separate project, just stop using Gradio

Rejected: this was the status quo immediately before this ADR (Gradio deleted, `tapio/` kept as an editable dependency of `backend/`). It preserves the indirection (extra lockfile, path dependency, `py.typed` marker) for no remaining benefit, since `backend/` is `tapio/`'s only consumer.

### Port the RAG/agent orchestration to TypeScript LangChain, run it inside the SvelteKit app

Rejected in the original backend-scaffolding discussion and not revisited here: TypeScript LangChain lags the Python ecosystem this project already depends on (LangChain, LangGraph, `langchain-chroma`, `langchain-huggingface`), and porting mid-migration would have multiplied risk for no clear payoff.

## References

- [ADR 0002: Split the repository into independent crawler, ingest, and app projects](0002-monorepo-service-split.md) — the `tapio/` portion of this split is superseded by this ADR; the `crawler`/`ingest` split stands unchanged.
- [ADR 0005: Use one shared, guide-led conversation for Tapio's multi-agent experience](0005-multi-agent-chat-experience.md)
- [Issue #36: Evaluate and plan UI beyond Gradio](https://github.com/Finntegrate/tapio/issues/36)
