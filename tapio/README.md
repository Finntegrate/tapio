# Tapio application

This service owns the user-facing RAG application. It only queries the configured vector collection; content collection and writes are owned by sibling services.

Run `uv sync`, then `uv run tapio serve`.
