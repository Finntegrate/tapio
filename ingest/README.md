# Tapio ingest

This service reads crawler Markdown and owns chunking and vector-store writes. Its only upstream contract is Markdown plus YAML frontmatter containing `source_url`.

Run `uv sync`, then `uv run tapio-ingest --help`.
