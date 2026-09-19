# Tapio

<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
[![All Contributors](https://img.shields.io/badge/all_contributors-3-orange.svg?style=flat-square)](#contributors-)
<!-- ALL-CONTRIBUTORS-BADGE:END -->
[![Service CI](https://github.com/Finntegrate/tapio/actions/workflows/ci.yaml/badge.svg)](https://github.com/Finntegrate/tapio/actions/workflows/ci.yaml)
[![License: EUPL-1.2](https://img.shields.io/badge/license-EUPL--1.2-blue.svg)](LICENSE)

**Tapio is a guide network that helps people navigate Finnish immigration — residence permits, employment, benefits, and housing — through one coordinated conversation grounded in official sources.**

Moving to a new country means learning an unfamiliar bureaucracy in a language you may not read fluently, from a dozen different authorities that don't talk to each other. Tapio is a first stop: it answers in plain language, tells you exactly which official page an answer came from, and hands you off to a specialist guide when your question crosses into their territory — all without asking who you are.

🔗 **Live roster and product overview:** [finntegrate.org/tapio](https://finntegrate.org/tapio/)

## Why Tapio

Finnish immigration information is scattered across Migri, Kela, TE-palvelut, municipal services, and more — written in dense administrative language, often only in Finnish and Swedish. People navigating this system are frequently non-native speakers under time pressure who don't yet know which authority to ask, or what to even call the thing they need.

A generic chatbot doesn't fix this: it hides who's answering, why an answer applies to your situation, and whether it's trustworthy enough to act on. Tapio is built around the opposite bet — that trust in an AI system navigating something this consequential comes from **visible expertise, cited sources, and a stated boundary of what it won't do**, not from a single black-box assistant that sounds confident about everything.

## What makes it different

- **A named guide network, not one assistant.** Tapio (the coordinator) and specialists like Ilmarinen, Sampo, Rauni, and Otso — each named for a figure from Finnish cultural heritage — handle distinct domains. You always know which guide answered and why it was brought in, and guides introduce each other by name mid-conversation, so you discover who else can help without reading a directory first.
- **Every substantive answer is sourced.** Answers cite the official page they came from. If no reliable source exists for a question, Tapio says so instead of guessing.
- **Proactive, not just reactive.** Newcomers often don't know what to ask next. Guides surface likely-relevant next steps tied to your situation, grounded in the same official sources as any direct answer.
- **One conversation, not a maze of tabs.** A permit question that turns into a benefits question stays in the same thread — no repeating your situation to a different tool.
- **Privacy by design, not by policy.** Tapio doesn't ask for or retain a case number, application status, or family details. Many people who rely on it — asylum seekers, undocumented people, people fleeing abuse — face real physical risk from a data exposure, so the product is built to have as little as possible to expose.
- **Knows its own boundary.** Tapio is explicit that it isn't a caseworker, legal representative, or official authority, and hands off to human or official support when a question needs one.

## Who it's for

- **Students** navigating study-related residence permits and enrollment
- **Workers** exploring employment-based permits, job seeking, and workplace rights
- **Families** pursuing reunification, or supporting a family member's application
- **Refugees and asylum seekers** needing guidance on process and available support
- **Partner organizations** — NGOs, employers, and municipalities — that refer clients to Tapio and want visibility into how it supports their own advising work

## How it works

```text
crawler  ── Markdown + source_url ──>  content/  ── embeddings ──>  vectorstore/  ──>  backend  ──>  app
```

A crawler collects official source pages, an ingestion pipeline chunks and embeds them into a vector store, and a FastAPI backend runs the multi-agent retrieval and routing logic ([LangGraph](https://www.langchain.com/langgraph)) behind a chat API. A SvelteKit web app is the reference client. See [Documentation](#documentation) below for the full architecture and product spec.

## Documentation

| Document | Covers |
| --- | --- |
| [Product requirements (PRD)](docs/PRD.md) | Product goals, the guide network, success metrics, open questions |
| [Architecture decision records](docs/ADRs/) | Why the system is built the way it is |
| [Specs](docs/specs/) | Detailed designs for specific subsystems (guardrails, multi-agent chat, the ontological harness, and more) |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development environment setup, running the pipeline locally, code style, and how to submit changes |
| [WORKFLOW.md](WORKFLOW.md) | How work is planned and triaged on the project board |

## Quick start

```bash
git clone https://github.com/Finntegrate/tapio.git
cd tapio
mise install                        # pinned dev tools
(cd crawler && uv sync) && (cd ingest && uv sync) && (cd backend && uv sync) && (cd app && npm install)
ollama pull gemma4:latest           # zero-setup local model — or configure a hosted provider, see below

mise run crawl && mise run ingest   # collect and index a source site (needs Chrome installed, see below)
mise run backend                    # start the API (in one terminal)
mise run app                        # start the chat client (in another)
```

You'll need the stable release of [Google Chrome](https://www.google.com/chrome/) installed: the crawler drives it directly and won't fall back to Chromium or another browser. Note that the crawl step fetches real pages from each configured source site (Migri, Kela, etc.) over the network like any web crawler — that traffic isn't privacy-isolated, and those sites see ordinary request metadata (your IP address, user agent).

The chat backend's LLM is provider-configurable, not local-only: the command above uses [Ollama](https://ollama.com/) because it needs no API key, but Tapio is moving toward commodity hosted providers (OpenAI, Anthropic, or any OpenAI-compatible endpoint) as the primary target — a local model is a heavier download and needs a machine capable of running it, which not every contributor has. Local inference stays available as a fallback for anyone who wants it (offline use, no chat traffic sent to a third party), just not the assumed default. See [backend/README.md](backend/README.md#configuration) for `TAPIO_LLM_PROVIDER` setup.

For prerequisites, troubleshooting, dev containers/Codespaces, and everything else needed to develop on Tapio, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Contributing

Contributions of any kind are welcome — code, documentation, translations, or source research. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, code style, and the pull request process.

## License

Licensed under the European Union Public License version 1.2. See [LICENSE](LICENSE) for details.

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
