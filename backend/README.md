# Tapio backend

FastAPI HTTP/SSE layer over Tapio's RAG and agent-routing orchestration, built for the SvelteKit `app/` frontend (see [ADR 0002](../docs/ADRs/0002-monorepo-service-split.md), [ADR 0005](../docs/ADRs/0005-multi-agent-chat-experience.md), and [ADR 0006](../docs/ADRs/0006-retire-gradio.md)).

This project owns both the orchestration logic (`RAGOrchestrator`, `AgentRouter`, the guide definitions, prompt templates) and the API that exposes it — the standalone `tapio/` project and its Gradio UI have been retired.

Run `uv sync`, then `uv run uvicorn app.main:app --reload --port 8000`. It reads the shared `../vectorstore/` collection written by `ingest/`; with the default `ollama` provider, requires a local Ollama instance with the configured model available.

## Configuration

### LLM provider (`TAPIO_LLM_` env vars)

The LLM backend is a plain [LangChain `BaseChatModel`](https://python.langchain.com/docs/concepts/chat_models/), selected at runtime via LangChain's own [`init_chat_model`](https://python.langchain.com/docs/how_to/chat_models_universal_init/) — no custom provider abstraction, and no code change needed to switch between a local Ollama model and a cloud provider (#9). `TAPIO_LLM_PROVIDER`'s values are exactly the provider names LangChain itself recognizes.

| Variable            | Default            | Purpose                                                                                                                                                                                    |
| -------------------- | ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `TAPIO_LLM_PROVIDER` | `ollama`            | `ollama` for the local Ollama runtime, `openai` for OpenAI (or any OpenAI-compatible endpoint, via `TAPIO_LLM_API_BASE` — see Scaleway below), or `anthropic` for Anthropic.             |
| `TAPIO_LLM_MODEL`    | `gemma4:latest`     | The model identifier, in whatever form the chosen provider expects, e.g. `gemma4:latest` (Ollama), `gpt-4o-mini` (OpenAI), `claude-3-5-haiku-20241022` (Anthropic).                      |
| `TAPIO_LLM_API_BASE` | unset               | Custom API base URL. For Ollama, points at a remote or non-default Ollama server. Required for Scaleway's Generative APIs and other self-hosted OpenAI-compatible endpoints (used with `TAPIO_LLM_PROVIDER=openai`); unused by OpenAI/Anthropic's own default endpoints. |
| `TAPIO_LLM_API_KEY`  | unset               | Explicit API key. When unset, each provider's LangChain integration falls back to its own standard environment variable (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`).                    |
| `TAPIO_LLM_MODEL_OVERRIDES` | unset        | JSON object giving individual guides or stages their own model — see [Per-guide and per-stage models](#per-guide-and-per-stage-models) below.                                                |

Example for OpenAI:

```bash
export TAPIO_LLM_PROVIDER=openai
export TAPIO_LLM_MODEL=gpt-4o-mini
export OPENAI_API_KEY=sk-...
```

Example for Anthropic:

```bash
export TAPIO_LLM_PROVIDER=anthropic
export TAPIO_LLM_MODEL=claude-3-5-haiku-20241022
export ANTHROPIC_API_KEY=sk-ant-...
```

Example for Scaleway's OpenAI-compatible endpoint:

```bash
export TAPIO_LLM_PROVIDER=openai
export TAPIO_LLM_MODEL=<scaleway-model-id>
export TAPIO_LLM_API_BASE=https://api.scaleway.ai/v1
export TAPIO_LLM_API_KEY=...
```

### Per-guide and per-stage models

By default every guide and the guardrail share the one model above. `TAPIO_LLM_MODEL_OVERRIDES` gives individual guides or stages their own — for example a small, fast model for guardrail checks and a stronger one for a specialist's answers. Anything without an entry keeps using `TAPIO_LLM_PROVIDER`/`TAPIO_LLM_MODEL`, so this is optional.

Keys are a guide id (`tapio`, `ilmarinen`, `sampo`, `rauni`, `otso`) or `guardrail` (message classification and the localized safety-response intro). An unknown key fails at startup. Values use the `provider:model` form, where the provider is one Tapio supports: `ollama`, `openai`, or `anthropic`. Other LangChain providers (such as `google_genai`) are rejected at startup, as is a near-miss of a supported name (such as `antropic`). A value without a provider prefix, such as an Ollama tag like `gemma4:e2b`, uses `TAPIO_LLM_PROVIDER`, and is only accepted when that is `ollama`; on a cloud default, prefix it (e.g. `openai:ft:gpt-4o-mini:...`).

```bash
export TAPIO_LLM_PROVIDER=ollama
export TAPIO_LLM_MODEL=gemma4:latest
export TAPIO_LLM_MODEL_OVERRIDES='{"guardrail": "gemma4:e2b", "ilmarinen": "anthropic:claude-haiku-4-5"}'
export ANTHROPIC_API_KEY=sk-ant-...
```

`TAPIO_LLM_API_BASE` and `TAPIO_LLM_API_KEY` apply only to models on `TAPIO_LLM_PROVIDER`. An override on a different provider uses that provider's own environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OLLAMA_HOST`, …), so a key or URL meant for one provider is never sent to another. `GET /health` checks the default model, every guide's model, and the guardrail's model, and reports each one under `models`.

## Agent tools

Which tools the agents may call is configuration, not code (`app.tools`). A tool is available only if it is not disabled, its cost tier is within the allowed maximum, and every env var it needs is set.

| Variable | Default | Description |
| --- | --- | --- |
| `TAPIO_TOOLS_DISABLED` | `[]` | JSON list of tool names to switch off, e.g. `'["add_calendar_days"]'`. An unknown name fails at startup. |
| `TAPIO_TOOLS_MAX_COST_TIER` | `free` | Most expensive tier allowed: `free`, `metered`, or `paid`. The default never spends money on tools. |

| Tool | Cost tier | Needs |
| --- | --- | --- |
| `get_current_datetime` | free | nothing |
| `add_calendar_days` | free | nothing |

Each call is logged with the tool's name and cost tier (never its input, which can contain user text).

## Endpoints

- `GET /health` — checks model availability: `model_available` is true only if every configured model is available, and `models` breaks it down by role (`default`, each overridden guide, `guardrail`).
- `GET /agents` — the guide roster (id, name, title, category, summary, color).
- `POST /chat/stream` — Server-Sent Events chat stream. Emits `routing`, `citation`, `token` (repeated), and `done` events per turn, or `error` on failure.

## Out of scope

Authentication, the sensitive-query guardrail classifier, conversation persistence/checkpointing, and rate limiting are not implemented here — see issues [#31](https://github.com/Finntegrate/tapio/issues/31), [#29](https://github.com/Finntegrate/tapio/issues/29), and [#16](https://github.com/Finntegrate/tapio/issues/16)/[#35](https://github.com/Finntegrate/tapio/issues/35).
