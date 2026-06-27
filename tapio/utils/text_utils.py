"""Utilities for text and HTML processing."""

import logging
import re
from typing import Any

# Import LangChain text splitters
from langchain_text_splitters import (  # type: ignore[import-not-found]
    HTMLHeaderTextSplitter,
    HTMLSectionSplitter,
    RecursiveCharacterTextSplitter,
)

logger = logging.getLogger(__name__)

# Content shorter than this is treated as too small to be worth chunking
MIN_CHUNKABLE_CONTENT_LENGTH = 100


def is_pdf_url(url: str) -> bool:
    """Check if a URL points to a PDF file.

    Args:
        url: URL to check

    Returns:
        True if the URL points to a PDF, False otherwise
    """
    # Check if URL ends with .pdf (case insensitive), or has "pdf" in the URL path
    return url.lower().endswith(".pdf") or "pdf" in url.rsplit("/", maxsplit=1)[-1].lower()


def chunk_html_content(
    html_content: str,
    content_type: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    splitter_type: str = "semantic",
    max_chunks: int = 50,  # Add a safety limit to prevent infinite chunking
) -> list[dict[str, Any]]:
    """Split HTML content into chunks using appropriate LangChain text splitters.

    Args:
        html_content: HTML content as string
        content_type: Content type string (to determine if it's HTML)
        chunk_size: Maximum chunk size in characters
        chunk_overlap: Overlap between chunks in characters
        splitter_type: Type of splitter to use ("semantic", "header", "section")
        max_chunks: Maximum number of chunks to prevent infinite chunking

    Returns:
        List of dictionaries with chunks and their metadata
    """
    # First, aggressively remove JavaScript code from HTML
    html_content = remove_javascript(html_content)

    # Sanity check for empty content
    if not html_content or len(html_content.strip()) < MIN_CHUNKABLE_CONTENT_LENGTH:
        logger.warning("Content is too short or empty, not chunking")
        return [{"content": html_content.strip(), "metadata": {}}]

    # Extract plain text for size estimation
    plain_text = re.sub(r"<[^>]+>", " ", html_content)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()

    # If the content is already small, don't bother chunking
    if len(plain_text) <= chunk_size:
        logger.info(
            "Content size (%d chars) is smaller than chunk_size (%d), skipping chunking",
            len(plain_text),
            chunk_size,
        )
        return [{"content": plain_text, "metadata": {}}]

    # Estimate reasonable number of chunks based on content size
    estimated_chunks = len(plain_text) // (chunk_size - chunk_overlap) + 1
    if estimated_chunks > max_chunks:
        logger.warning(
            "Content would generate too many chunks (%d). Using simpler chunking method.",
            estimated_chunks,
        )
        # Fall back to simple text splitting for very large content
        return _chunk_text_safely(plain_text, chunk_size, chunk_overlap, max_chunks)

    # If not HTML content, use default recursive text splitter
    if not content_type or "text/html" not in content_type.lower():
        return _chunk_text_safely(plain_text, chunk_size, chunk_overlap, max_chunks)

    # For HTML content, use the appropriate splitter based on the type
    try:
        if splitter_type == "header":
            # Use header-based chunking
            logger.info("Using header-based HTML chunking")
            headers_to_split_on = [
                ("h1", "Header 1"),
                ("h2", "Header 2"),
                ("h3", "Header 3"),
                ("h4", "Header 4"),
                ("h5", "Header 5"),
            ]
            html_splitter = HTMLHeaderTextSplitter(headers_to_split_on)
            split_docs = html_splitter.split_text(html_content)

        elif splitter_type == "section":
            # Use section-based chunking
            logger.info("Using section-based HTML chunking")
            headers_to_split_on = [
                ("h1", "Header 1"),
                ("h2", "Header 2"),
                ("h3", "Header 3"),
                ("h4", "Header 4"),
                ("h5", "Header 5"),
            ]
            # Using HTMLSectionSplitter but var type should match the interface
            section_splitter: HTMLHeaderTextSplitter = HTMLSectionSplitter(headers_to_split_on)  # type: ignore[assignment]
            split_docs = section_splitter.split_text(html_content)

        else:
            # For semantic chunking, try simpler approach first for better reliability
            logger.info("Using recursive character-based text chunking for HTML")
            # Extract text and chunk it, preserving some basic HTML structure
            cleaned_html = _basic_clean_html(html_content)
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
            )
            split_docs = text_splitter.create_documents([cleaned_html])

        # Apply safety checks
        if len(split_docs) > max_chunks:
            logger.warning(
                "HTML splitting produced too many chunks (%d). Limiting to %d.",
                len(split_docs),
                max_chunks,
            )
            split_docs = split_docs[:max_chunks]

        # Convert to our expected format
        return [{"content": doc.page_content, "metadata": doc.metadata} for doc in split_docs]

    except Exception:
        logger.warning("Error using HTML splitter. Falling back to default chunker.", exc_info=True)
        # Fallback to basic text splitting
        return _chunk_text_safely(plain_text, chunk_size, chunk_overlap, max_chunks)


def remove_javascript(html_content: str) -> str:
    """Aggressively remove all JavaScript code from HTML.

    Args:
        html_content: HTML content as string

    Returns:
        HTML content with JavaScript removed
    """
    # Remove all <script> tags and their contents
    cleaned = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL)

    # Remove onclick, onload and other JavaScript event attributes
    cleaned = re.sub(r' on\w+="[^"]*"', "", cleaned)
    cleaned = re.sub(r" on\w+='[^']*'", "", cleaned)

    # Remove JavaScript: URLs
    cleaned = re.sub(r'href="javascript:[^"]*"', 'href="#"', cleaned)
    cleaned = re.sub(r"href='javascript:[^']*'", "href='#'", cleaned)

    # Remove inline JS that might have been missed
    return re.sub(r"(\s)javascript:", r"\1", cleaned)


def _chunk_text_safely(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    max_chunks: int = 50,
) -> list[dict[str, Any]]:
    """Safe text chunking with limits to prevent infinite loops."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    try:
        docs = text_splitter.create_documents([text])

        # Safety check for too many chunks
        if len(docs) > max_chunks:
            logger.warning(
                "Generated too many chunks (%d). Limiting to %d.",
                len(docs),
                max_chunks,
            )
            docs = docs[:max_chunks]

        return [{"content": doc.page_content, "metadata": {}} for doc in docs]
    except Exception:
        logger.exception("Error chunking text")
        # Last resort: manual chunking
        chunks = []
        for i in range(0, len(text), chunk_size - chunk_overlap):
            chunk = text[i : i + chunk_size]
            chunks.append({"content": chunk, "metadata": {}})
            if len(chunks) >= max_chunks:
                break
        return chunks


def _basic_clean_html(html_content: str) -> str:
    """Perform basic HTML cleaning to make text chunking more reliable.

    Preserves important structural elements.
    """
    # Remove script and style tags with their content
    cleaned = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL)
    cleaned = re.sub(r"<style[^>]*>.*?</style>", "", cleaned, flags=re.DOTALL)

    # Remove comments
    cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)

    # Convert headers to plain text with newlines
    cleaned = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n\n# \1\n\n", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n\n## \1\n\n", cleaned, flags=re.DOTALL)
    cleaned = re.sub(
        r"<h3[^>]*>(.*?)</h3>",
        r"\n\n### \1\n\n",
        cleaned,
        flags=re.DOTALL,
    )

    # Convert paragraphs and breaks to newlines
    cleaned = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\n\1\n\n", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"<br[^>]*>", "\n", cleaned)

    # Convert lists to text with bullet points
    cleaned = re.sub(r"<li[^>]*>(.*?)</li>", r"\n• \1", cleaned, flags=re.DOTALL)

    # Remove other HTML tags
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)

    # Fix whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\n\s+\n", "\n\n", cleaned)

    return cleaned.strip()
