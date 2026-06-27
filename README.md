# Tapio
<!-- ALL-CONTRIBUTORS-BADGE:START - Do not remove or modify this section -->
[![All Contributors](https://img.shields.io/badge/all_contributors-3-orange.svg?style=flat-square)](#contributors-)
<!-- ALL-CONTRIBUTORS-BADGE:END -->

Tapio is a RAG (Retrieval Augmented Generation) tool for extracting, processing, and querying information from websites like Migri.fi (Finnish Immigration Service). It provides complete workflow capabilities including web crawling, content parsing, vectorization, and an interactive chatbot interface.

## Features
- **Multi-site support** - Configurable site-specific crawling and parsing
- **End-to-end pipeline** - Crawl → Parse → Vectorize → Query workflow
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

## Installation and Setup

### Prerequisites
- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) - Fast Python package installer
- [Ollama](https://ollama.ai/) - For local LLM inference

### Quick Start

1. Clone and setup:
```bash
git clone https://github.com/Finntegrate/tapio.git
cd tapio
uv sync
```

2. Install required Ollama model:
```bash
ollama pull llama3.2
```

## Usage

### CLI Overview

Tapio provides a four-step workflow:

1. **crawl** - Collect HTML content from websites
2. **parse** - Convert HTML to structured Markdown
3. **vectorize** - Create vector embeddings for semantic search
4. **tapio-app** - Launch the interactive chatbot interface

Use `uv run -m tapio.cli --help` to see all commands or `uv run -m tapio.cli <command> --help` for command-specific options.

### Quick Example

Complete workflow for the Migri website:

```bash
# 1. Crawl content (uses site configuration)
uv run -m tapio.cli crawl migri --depth 2

# 2. Parse HTML to Markdown
uv run -m tapio.cli parse migri

# 3. Create vector embeddings
uv run -m tapio.cli vectorize

# 4. Launch chatbot interface
uv run -m tapio.cli tapio-app
```

### Available Sites

To list configured sites:
```bash
uv run -m tapio.cli list-sites
```

To view detailed site configurations:
```bash
uv run -m tapio.cli list-sites --verbose
```

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
