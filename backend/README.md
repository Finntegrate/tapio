# Tapio backend

FastAPI HTTP/SSE layer over Tapio's RAG and agent-routing orchestration, built for the SvelteKit `app/` frontend (see [ADR 0002](../docs/ADRs/0002-monorepo-service-split.md), [ADR 0005](../docs/ADRs/0005-multi-agent-chat-experience.md), and [ADR 0006](../docs/ADRs/0006-retire-gradio.md)).

This project owns both the orchestration logic (`RAGOrchestrator`, `AgentRouter`, the guide definitions, prompt templates) and the API that exposes it — the standalone `tapio/` project and its Gradio UI have been retired.

Run `uv sync`, then `uv run uvicorn app.main:app --reload --port 8000`. It reads the shared `../vectorstore/` collection written by `ingest/`; requires a local Ollama instance with the configured model available.

## Endpoints

- `GET /health` — checks Ollama/model availability.
- `GET /agents` — the guide roster (id, name, title, category, summary, color).
- `POST /chat/stream` — Server-Sent Events chat stream. Emits `routing`, `citation`, `token` (repeated), and `done` events per turn, or `error` on failure.

## Out of scope

Authentication, the sensitive-query guardrail classifier, conversation persistence/checkpointing, and rate limiting are not implemented here — see issues [#31](https://github.com/Finntegrate/tapio/issues/31), [#29](https://github.com/Finntegrate/tapio/issues/29), and [#16](https://github.com/Finntegrate/tapio/issues/16)/[#35](https://github.com/Finntegrate/tapio/issues/35).
