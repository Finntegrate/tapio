# Tapio ingest

This service reads crawler Markdown and owns chunking and vector-store writes.
Its only upstream contract is Markdown files in the shared content directory
with YAML frontmatter containing `source_url`; it does not import or invoke the
crawler.

Locally, both services default to the repository's `content/` directory. In
deployment, mount one directory into both services and set `TAPIO_CONTENT_DIR`
to that mount path. Then run:

```bash
uv sync
uv run tapio-ingest
```

The vector collection is written to the repository's shared `vectorstore/`
directory by default. Set `TAPIO_VECTORSTORE_DIR` to use a mounted vector-store
directory instead.

Pass a different source explicitly when needed, or restrict a run to one
crawler site:

```bash
uv run tapio-ingest /shared/content --site migri
```
