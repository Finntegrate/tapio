"""Vectorize markdown content into ChromaDB using LangChain components."""

import logging
import os
from typing import Any

from langchain_chroma import Chroma  # type: ignore[import-not-found]
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownTextSplitter  # type: ignore[import-not-found]

from tapio.utils.markdown_utils import find_markdown_files, read_markdown_file

logger = logging.getLogger(__name__)


class MarkdownVectorizer:
    """Vectorize markdown content and store in ChromaDB using LangChain.

    This class handles the vectorization pipeline for markdown documents,
    including text splitting and storage in a vector database. Dependencies
    are injected to enable testing and configuration flexibility.
    """

    def __init__(
        self,
        vector_db: Chroma,
        text_splitter: MarkdownTextSplitter,
    ) -> None:
        """Initialize the vectorizer.

        Args:
            vector_db: LangChain Chroma instance for vector storage
            text_splitter: MarkdownTextSplitter for chunking documents

        Example:
            >>> from langchain_chroma import Chroma
            >>> from langchain_huggingface import HuggingFaceEmbeddings
            >>> from langchain_text_splitters import MarkdownTextSplitter
            >>>
            >>> embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
            >>> vector_db = Chroma(
            ...     collection_name="my_docs",
            ...     embedding_function=embeddings,
            ...     persist_directory="./chroma_db"
            ... )
            >>> text_splitter = MarkdownTextSplitter(chunk_size=1000, chunk_overlap=200)
            >>> vectorizer = MarkdownVectorizer(vector_db, text_splitter)
        """
        self.vector_db = vector_db
        self.text_splitter = text_splitter

        logger.debug("Initialized MarkdownVectorizer")

    def process_directory(
        self,
        input_dir: str,
        site_filter: str | None = None,
        batch_size: int = 20,
    ) -> int:
        """
        Process all markdown files in a directory.

        Args:
            input_dir: Directory containing markdown files
            site_filter: Optional filter for specific site
            batch_size: Number of files to process in a batch

        Returns:
            Number of files successfully processed
        """
        # Find all markdown files
        markdown_files = find_markdown_files(input_dir, site_filter)
        total_files = len(markdown_files)

        logger.info(f"Found {total_files} markdown files to process")

        # Process files in batches
        processed_count = 0
        chunk_count = 0
        for i in range(0, total_files, batch_size):
            batch = markdown_files[i : i + batch_size]
            new_chunks = self._process_batch(batch)
            processed_count += len(batch)
            chunk_count += new_chunks
            logger.info(
                f"Processed {processed_count}/{total_files} files ({chunk_count} chunks)",
            )

        return processed_count

    def _process_batch(self, file_paths: list[str]) -> int:
        """
        Process a batch of markdown files.

        Args:
            file_paths: List of paths to markdown files

        Returns:
            Number of chunks processed
        """
        all_documents = []

        for file_path in file_paths:
            try:
                # Read markdown file
                metadata, content = read_markdown_file(file_path)

                if not content:
                    logger.warning(f"Empty content in {file_path}")
                    continue

                # Create a LangChain Document with metadata
                doc = Document(
                    page_content=content,
                    metadata=self._prepare_metadata(metadata, file_path),
                )

                # Split the document and add source info to each chunk
                chunks = self.text_splitter.split_documents([doc])

                # Update metadata with chunk information
                for i, chunk in enumerate(chunks):
                    chunk.metadata["chunk_index"] = i
                    chunk.metadata["total_chunks"] = len(chunks)

                all_documents.extend(chunks)

                logger.debug(
                    f"Added document {os.path.basename(file_path)} with embeddings",
                )

            except Exception as e:
                logger.error(f"Error processing file {file_path}: {e}")

        # Add all documents to the vector store
        if all_documents:
            self.vector_db.add_documents(all_documents)

        return len(all_documents)

    def _prepare_metadata(
        self,
        metadata: dict[str, Any],
        file_path: str,
    ) -> dict[str, Any]:
        """
        Prepare metadata for the document.

        Args:
            metadata: Original metadata from the markdown file
            file_path: Path to the markdown file

        Returns:
            Enhanced metadata dictionary
        """
        # Extract document ID from filename
        doc_id = os.path.splitext(os.path.basename(file_path))[0]

        # Start with the metadata from the markdown frontmatter
        enriched_metadata = metadata.copy()

        # Add additional useful metadata
        enriched_metadata["source_id"] = doc_id
        enriched_metadata["source_path"] = file_path
        enriched_metadata["file_name"] = os.path.basename(file_path)

        # Ensure source URL is preserved for citation purposes
        if "source_url" in metadata:
            enriched_metadata["source_url"] = metadata["source_url"]
            # Also add as url for compatibility with existing code
            enriched_metadata["url"] = metadata["source_url"]
        elif "url" in metadata:
            # If url already exists but source_url doesn't, preserve it
            enriched_metadata["source_url"] = metadata["url"]

        # Add a dedicated citation_url field for retrieval augmented generation
        if "source_url" in enriched_metadata:
            enriched_metadata["citation_url"] = enriched_metadata["source_url"]
        elif "url" in enriched_metadata:
            enriched_metadata["citation_url"] = enriched_metadata["url"]

        return enriched_metadata

    def process_file(self, file_path: str) -> int:
        """
        Process a single markdown file.

        Args:
            file_path: Path to markdown file

        Returns:
            Number of chunks processed
        """
        try:
            # Read markdown file
            metadata, content = read_markdown_file(file_path)

            if not content:
                logger.warning(f"Empty content in {file_path}")
                return 0

            # Create a LangChain Document
            doc = Document(
                page_content=content,
                metadata=self._prepare_metadata(metadata, file_path),
            )

            # Split the document
            chunks = self.text_splitter.split_documents([doc])

            # Update metadata with chunk information
            for i, chunk in enumerate(chunks):
                chunk.metadata["chunk_index"] = i
                chunk.metadata["total_chunks"] = len(chunks)

            # Add documents to the vector store
            self.vector_db.add_documents(chunks)
            # No need to explicitly persist as ChromaDB 0.4.x+ automatically persists documents

            logger.debug(
                f"Added document {os.path.basename(file_path)} with embeddings",
            )

            return len(chunks)

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            return 0
