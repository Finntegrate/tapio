# Tapio
<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
[![All Contributors](https://img.shields.io/badge/all_contributors-3-orange.svg?style=flat-square)](#contributors-)
<!-- ALL-CONTRIBUTORS-BADGE:END -->

Tapio is a RAG (Retrieval Augmented Generation) tool for extracting, processing, and querying information from websites like Migri.fi (Finnish Immigration Service). Its crawler, ingestion pipeline, and chat application are independent projects in this monorepo.

## Projects

- `crawler/` collects source pages and emits Markdown with `source_url` frontmatter.
- `ingest/` chunks that Markdown and writes it to the shared `vectorstore/` collection.
- `backend/` owns the RAG/agent-routing orchestration and only reads from that collection, exposing it as a FastAPI HTTP/SSE API.
- `app/` is the SvelteKit chat client that calls `backend/`.

`crawler/`, `ingest/`, and `backend/` each have their own dependency manifest and
can be tested independently with `mise run test:crawl`, `mise run test:ingest`, or
`mise run test:backend`. `app/` is tested with `npm run test:unit` (see its own README).

```text
crawler  ── Markdown + source_url ──>  content/  ── embeddings ──>  vectorstore/  ──>  backend  ──>  app
```

`content/` and `vectorstore/` are local runtime data, not source code. They
are ignored by Git and are the only handoffs between the services.

## Features

- **Multi-site support** - Configurable site-specific crawling and extraction
- **End-to-end pipeline** - Crawl → Ingest → Query workflow
- **Local LLM integration** - Uses Ollama for private, local inference
- **Semantic search** - ChromaDB vector database for relevant content retrieval
- **Interactive chatbot** - Web interface for natural language queries
- **Flexible crawling** - Configurable depth and domain restrictions
- **Comprehensive testing** - Full test suite for reliability

## Target Use Cases

**Primary Users:** EU and non-EU citizens navigating Finnish immigration processes

- Students seeking education information
- Workers exploring employment options
- Families pursuing reunification
- Refugees and asylum seekers needing guidance

**Core Needs:**

- Finding relevant, accurate information quickly
- Practice conversations on specific topics (family reunification, work permits, etc.)

## Run the pipeline

### Prerequisites

- [mise](https://mise.jdx.dev/) to install and run the pinned development tools
- Network access for the initial Crawl4AI browser and embedding-model downloads
- [Ollama](https://ollama.com/) running locally, for the chat model

### System requirements

- Enough available RAM for the selected Ollama model; `gemma4:latest` is the default
- For low-resource environments such as GitHub Codespaces, choose a smaller model explicitly with `--model-name`

### First-time setup

Clone the repository, then install the tools specified in `mise.toml`, prepare
each service environment, install Google Chrome for the crawler, and download
the chat model:

```bash
git clone https://github.com/Finntegrate/tapio.git
cd tapio

mise install

(cd crawler && uv sync)
(cd ingest && uv sync)
(cd backend && uv sync)
(cd app && npm install)

ollama pull gemma4:latest
```

### End-to-end quick start

Run these commands from the repository root, in this order:

```bash
# 1. Crawl every configured site using its configured depth, limits, and schedule.
mise run crawl

# 2. Chunk and embed the Markdown written to content/.
mise run ingest

# 3. Start the backend API, which reads vectorstore/.
mise run backend

# 4. In a second terminal, start the SvelteKit chat client.
mise run app
```

The crawler respects each site's `recrawl_interval_hours`; a site that is not
due is skipped. It attempts every configured site even if an earlier one fails,
then returns a non-zero status if any site failed. When new pages are crawled,
rerun `mise run ingest`, then restart the backend (`backend/` is what reads
`vectorstore/`; the SvelteKit `app/` only calls the backend's API) so it opens
the refreshed vector collection.

### Shared runtime directories

| Directory | Written by | Read by | Local default | Deployment setting |
| --- | --- | --- | --- | --- |
| `content/` | `crawler` | `ingest` | repository root | `TAPIO_CONTENT_DIR` |
| `vectorstore/` | `ingest` | `backend` | repository root | `TAPIO_VECTORSTORE_DIR` |

For deployment, mount the same content volume in `crawler` and `ingest`, and
the same vector-store volume in `ingest` and `backend`. Set the corresponding
environment variable to the mount path in each service. The services share
files only; they do not import, invoke, or otherwise depend on one another.

### Mise task reference

| Command | Purpose |
| --- | --- |
| `mise run crawl` | Crawl every configured site with its configured settings; attempt all sites before reporting failures. |
| `mise run ingest` | Ingest all crawler Markdown from `content/` into `vectorstore/`. |
| `mise run backend` | Start the FastAPI backend, which reads `vectorstore/`. |
| `mise run app` | Start the SvelteKit chat client's dev server. |
| `mise run test:crawl` | Run the crawler test suite. |
| `mise run test:ingest` | Run the ingestion test suite. |
| `mise run test:backend` | Run the backend test suite. |

Pass ingestion options after `--`:

```bash
# Re-ingest one site's Markdown only.
mise run ingest -- --site migri
```

### Work with an individual site

The root crawl task intentionally collects every configured source. For a
single-site crawl or a shallow smoke test, use the crawler CLI directly:

```bash
cd crawler
uv run tapio-crawler list-sites
uv run tapio-crawler crawl migri --depth 0
```

Then return to the repository root and run `mise run ingest -- --site migri`.

### Troubleshooting

- **“No relevant documents found”** — Run `mise run ingest` after a crawl and
  restart the backend. The backend must be started after the shared vector
  collection has been written.
- **Crawl4AI cannot start a browser** — Install the stable Google Chrome
  release through your operating system. Crawl4AI launches it through
  Playwright's `chrome` channel.
- **The app cannot generate an answer** — Ensure the Ollama service is running
  and the selected model has been pulled, for example `ollama pull gemma4:latest`.
- **A mounted directory is not used** — Set `TAPIO_CONTENT_DIR` and/or
  `TAPIO_VECTORSTORE_DIR` to the absolute mount path before running the relevant
  service.

For technical details on site configurations, programmatic API usage, and adding new sites, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines, code style requirements, and how to submit pull requests.

## License

Licensed under the European Union Public License version 1.2. See LICENSE for details.

## Contributors ✨

Thanks goes to these wonderful people ([emoji key](https://allcontributors.org/docs/en/emoji-key)):

<!-- ALL-CONTRIBUTORS-LIST:START - Do not remove or modify this section -->
<!-- prettier-ignore-start -->
<!-- markdownlint-disable -->
<table>
  <tbody>
    <tr>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/brylie"><img src="https://avatars.githubusercontent.com/u/17307?v=4?s=100" width="100px;" alt="Brylie Christopher Oxley"/><br /><sub><b>Brylie Christopher Oxley</b></sub></a><br /><a href="#infra-brylie" title="Infrastructure (Hosting, Build-Tools, etc)">🚇</a> <a href="https://github.com/finntegrate/tapio/commits?author=brylie" title="Tests">⚠️</a> <a href="https://github.com/finntegrate/tapio/commits?author=brylie" title="Documentation">📖</a> <a href="https://github.com/finntegrate/tapio/issues?q=author%3Abrylie" title="Bug reports">🐛</a> <a href="#business-brylie" title="Business development">💼</a> <a href="#content-brylie" title="Content">🖋</a> <a href="#ideas-brylie" title="Ideas, Planning, & Feedback">🤔</a> <a href="#maintenance-brylie" title="Maintenance">🚧</a> <a href="#mentoring-brylie" title="Mentoring">🧑‍🏫</a> <a href="#projectManagement-brylie" title="Project Management">📆</a> <a href="#promotion-brylie" title="Promotion">📣</a> <a href="#research-brylie" title="Research">🔬</a> <a href="https://github.com/finntegrate/tapio/pulls?q=is%3Apr+reviewed-by%3Abrylie" title="Reviewed Pull Requests">👀</a> <a href="https://github.com/finntegrate/tapio/commits?author=brylie" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://akikurvinen.fi/"><img src="https://avatars.githubusercontent.com/u/74042688?v=4?s=100" width="100px;" alt="AkiKurvinen"/><br /><sub><b>AkiKurvinen</b></sub></a><br /><a href="#data-AkiKurvinen" title="Data">🔣</a> <a href="https://github.com/finntegrate/tapio/commits?author=AkiKurvinen" title="Code">💻</a></td>
      <td align="center" valign="top" width="14.28%"><a href="https://github.com/ResendeTech"><img src="https://avatars.githubusercontent.com/u/142721352?v=4?s=100" width="100px;" alt="ResendeTech"/><br /><sub><b>ResendeTech</b></sub></a><br /><a href="https://github.com/finntegrate/tapio/commits?author=ResendeTech" title="Code">💻</a></td>
    </tr>
  </tbody>
</table>

<!-- markdownlint-restore -->
<!-- prettier-ignore-end -->

<!-- ALL-CONTRIBUTORS-LIST:END -->

This project follows the [all-contributors](https://github.com/all-contributors/all-contributors) specification. Contributions of any kind welcome!
