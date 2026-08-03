"""Utility modules for Tapio Assistant."""

# Import and expose functions from embedding_utils
from tapio.utils.embedding_utils import EmbeddingGenerator

# Import and expose functions from text_utils
from tapio.utils.text_utils import (
    chunk_html_content,
    is_pdf_url,
    remove_javascript,
)

__all__ = [
    "EmbeddingGenerator",
    "chunk_html_content",
    "is_pdf_url",
    "remove_javascript",
]
