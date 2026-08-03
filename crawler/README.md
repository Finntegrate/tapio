# Tapio crawler

This service owns source-site configuration and produces Markdown documents with `source_url` frontmatter. It does not access the vector store or serve user requests.

Run `uv sync`, then install Crawl4AI's Playwright/Patchright browser binaries once:

```bash
uv run crawl4ai-setup
```

Collect a configured site directly into `content/{site}/parsed/` Markdown:

```bash
uv run tapio-crawler crawl migri
```

Use `--depth 0` for a single-page smoke test. Each saved document includes
`title`, `source_url`, and `crawl_timestamp` YAML frontmatter for ingestion.
