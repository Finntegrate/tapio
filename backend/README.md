# Tapio backend

FastAPI HTTP/SSE layer over Tapio's RAG and agent-routing orchestration, built for the SvelteKit `app/` frontend (see [ADR 0002](../docs/ADRs/0002-monorepo-service-split.md), [ADR 0005](../docs/ADRs/0005-multi-agent-chat-experience.md), and [ADR 0006](../docs/ADRs/0006-retire-gradio.md)).

This project owns both the orchestration logic (`RAGOrchestrator`, `AgentRouter`, the guide definitions, prompt templates) and the API that exposes it — the standalone `tapio/` project and its Gradio UI have been retired.

Run `uv sync`, then `uv run uvicorn app.main:app --reload --port 8000`. It reads the shared `../vectorstore/` collection written by `ingest/`; with the default `ollama` provider, requires a local Ollama instance with the configured model available.

## Configuration

### LLM provider (`TAPIO_LLM_` env vars)

The LLM backend is swappable via configuration — no code change needed to switch between a local Ollama model and a cloud provider (#9).

| Variable            | Default            | Purpose                                                                                                                                                                                    |
| -------------------- | ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TAPIO_LLM_PROVIDER` | `ollama`            | `ollama` for the local Ollama runtime, or `litellm` for OpenAI, Anthropic, Scaleway, and other OpenAI-compatible endpoints (via [LiteLLM](https://docs.litellm.ai/)).                    |
| `TAPIO_LLM_MODEL`    | `gemma4:latest`     | For `ollama`, a plain Ollama model tag. For `litellm`, a LiteLLM model string, e.g. `openai/gpt-4o-mini`, `anthropic/claude-3-5-haiku-20241022`, or `openai/<model-id>` for an OpenAI-compatible endpoint used together with `TAPIO_LLM_API_BASE`. |
| `TAPIO_LLM_API_BASE` | unset               | Custom API base URL, passed straight to LiteLLM. Required for Scaleway's Generative APIs and other self-hosted OpenAI-compatible endpoints.                                              |
| `TAPIO_LLM_API_KEY`  | unset               | Explicit API key, passed straight to LiteLLM. When unset, LiteLLM falls back to the provider's standard environment variable (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).               |

Example for OpenAI:

```bash
export TAPIO_LLM_PROVIDER=litellm
export TAPIO_LLM_MODEL=openai/gpt-4o-mini
export OPENAI_API_KEY=sk-...
```

Example for Scaleway's OpenAI-compatible endpoint:

```bash
export TAPIO_LLM_PROVIDER=litellm
export TAPIO_LLM_MODEL=openai/<scaleway-model-id>
export TAPIO_LLM_API_BASE=https://api.scaleway.ai/v1
export TAPIO_LLM_API_KEY=...
```

## Endpoints

- `GET /health` — checks Ollama/model availability.
- `GET /agents` — the guide roster (id, name, title, category, summary, color).
- `POST /chat/stream` — Server-Sent Events chat stream. Emits `routing`, `citation`, `token` (repeated), and `done` events per turn, or `error` on failure.

## Out of scope

Authentication, the sensitive-query guardrail classifier, conversation persistence/checkpointing, and rate limiting are not implemented here — see issues [#31](https://github.com/Finntegrate/tapio/issues/31), [#29](https://github.com/Finntegrate/tapio/issues/29), and [#16](https://github.com/Finntegrate/tapio/issues/16)/[#35](https://github.com/Finntegrate/tapio/issues/35).
