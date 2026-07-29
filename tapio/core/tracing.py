"""LangSmith tracing setup for the Tapio application.

Provides a ``setup_langsmith`` function that configures LangSmith tracing
from environment variables (or a ``.env`` file).  Tracing is a no-op when
no LangSmith API key is configured, so it is safe to call unconditionally.

Also provides utilities for extracting and tracing structured metadata
(retrieved chunk IDs, source URLs, titles, etc.) from LangChain documents
so they are visible as structured fields in the LangSmith UI.
"""

import logging
import os
from typing import Any

from dotenv import load_dotenv
from langsmith import traceable

from tapio.config.settings import LANGSMITH_ENV_VARS

logger = logging.getLogger(__name__)


def setup_langsmith(project_name: str | None = None) -> None:
    """Configure LangSmith tracing for the application.

    Loads environment variables from a ``.env`` file if one exists, then
    sets the standard LangChain/LangSmith environment variables to their
    configured values.  If no API key is found, tracing is a silent no-op.

    Call this once at application startup, ideally before any LangChain
    or LangSmith components are imported (setting env vars before import
    is the most reliable approach).

    Args:
        project_name: Override for the LangSmith project name.  Falls back
            to the ``LANGCHAIN_PROJECT`` env var, then ``"tapio"``.
    """
    load_dotenv()

    for key, default in LANGSMITH_ENV_VARS.items():
        if key not in os.environ:
            os.environ.setdefault(key, default)

    if project_name is not None:
        os.environ["LANGCHAIN_PROJECT"] = project_name

    api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    project = os.environ.get("LANGCHAIN_PROJECT", "tapio")

    if api_key:
        logger.info(
            "LangSmith tracing enabled for project '%s' at %s",
            project,
            os.environ.get("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com"),
        )
    else:
        logger.info(
            "LangSmith not configured — set LANGSMITH_API_KEY in .env to enable tracing",
        )


def extract_document_metadata(documents: list[Any]) -> list[dict[str, Any]]:
    """Extract structured metadata from documents for LangSmith tracing.

    Pulls out chunk IDs, source URLs, titles, headers, and other relevant
    fields that are useful to inspect in a trace.  Handles missing or
    non-dict metadata gracefully.

    Args:
        documents: List of LangChain ``Document`` objects (or anything with
            a ``metadata`` dict attribute).

    Returns:
        List of metadata dicts — one per document — with structured keys.
    """
    metadata_list: list[dict[str, Any]] = []

    for doc in documents:
        if not hasattr(doc, "metadata") or not isinstance(doc.metadata, dict):
            metadata_list.append({})
            continue

        doc_meta = doc.metadata

        raw = getattr(doc, "page_content", None)
        content = raw if isinstance(raw, str) else ""

        entry: dict[str, Any] = {
            "source_id": doc_meta.get("source_id"),
            "source_url": doc_meta.get("source_url") or doc_meta.get("url"),
            "citation_url": doc_meta.get("citation_url"),
            "title": doc_meta.get("title"),
            "chunk_index": doc_meta.get("chunk_index"),
            "total_chunks": doc_meta.get("total_chunks"),
            "file_name": doc_meta.get("file_name"),
            "content_preview": content[:500] + ("..." if len(content) > 500 else ""),
        }

        known_keys = {
            "source_id",
            "source_url",
            "url",
            "citation_url",
            "title",
            "chunk_index",
            "total_chunks",
            "file_name",
            "source_path",
            "content_preview",
        }

        extra = {k: v for k, v in doc_meta.items() if k not in known_keys}
        if extra:
            entry["extra_metadata"] = extra

        metadata_list.append(entry)

    return metadata_list


@traceable(run_type="retriever", name="Retrieval Metadata")
def trace_retrieval_metadata(documents: list[Any]) -> list[dict[str, Any]]:
    """Trace the metadata of retrieved documents as a structured LangSmith node.

    Creates a visible trace node containing chunk IDs, source URLs, titles,
    and other per-document metadata — making it easy to inspect what was
    retrieved directly in the LangSmith UI.

    Intended to be called from ``DocumentRetrievalService.retrieve_documents``
    after the vector store query completes.

    Args:
        documents: List of retrieved documents.

    Returns:
        Structured metadata list that becomes the trace output.
    """
    return extract_document_metadata(documents)
