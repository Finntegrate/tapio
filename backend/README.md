# Tapio backend

FastAPI HTTP/SSE layer over the `tapio/` RAG and agent-routing orchestration, built for the SvelteKit `app/` frontend (see [ADR 0002](../docs/ADRs/0002-monorepo-service-split.md) and [ADR 0005](../docs/ADRs/0005-multi-agent-chat-experience.md)).

It depends on `tapio/` as a local editable package rather than duplicating orchestration logic — `RAGOrchestrator`, `AgentRouter`, and the guide definitions all come from there unchanged.

Run `uv sync`, then `uv run uvicorn tapio_backend.main:app --reload --port 8000`. It reads the same `../vectorstore/` collection as `tapio/`; requires a local Ollama instance with the configured model available (see `tapio/README.md`).

## Endpoints

- `GET /health` — checks Ollama/model availability.
- `GET /agents` — the guide roster (id, name, title, category, summary, color).
- `POST /chat/stream` — Server-Sent Events chat stream. Emits `routing`, `citation`, `token` (repeated), and `done` events per turn, or `error` on failure.

## Out of scope

Authentication, the sensitive-query guardrail classifier, conversation persistence/checkpointing, and rate limiting are not implemented here — see issues [#31](https://github.com/Finntegrate/tapio/issues/31), [#29](https://github.com/Finntegrate/tapio/issues/29), and [#16](https://github.com/Finntegrate/tapio/issues/16)/[#35](https://github.com/Finntegrate/tapio/issues/35).
