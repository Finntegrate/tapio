"""Utilities for working with markdown content."""

import logging
from pathlib import Path

import frontmatter  # type: ignore[import-untyped]

from tapio.config.settings import DEFAULT_DIRS

logger = logging.getLogger(__name__)


def read_markdown_file(file_path: str) -> tuple[dict, str]:
    """Read a markdown file with frontmatter and return the metadata and content separately.

    Args:
        file_path: Path to the markdown file

    Returns:
        Tuple containing the metadata dictionary and content string
    """
    try:
        with Path(file_path).open(encoding="utf-8") as f:
            post = frontmatter.load(f)
            metadata = post.metadata
            content = post.content

            # Handle source URL from metadata - prioritize source_url added by parser
            if "source_url" in metadata:
                # A direct URL from our crawler mapping
                metadata["url"] = metadata["source_url"]
            elif "source_file" in metadata:
                # Fallback to legacy handling
                source_file = metadata["source_file"]
                if isinstance(source_file, str):
                    metadata["url"] = source_file.replace(f"{DEFAULT_DIRS['CRAWLED_DIR']}/", "")

            return metadata, content
    except Exception:
        logger.exception("Error reading markdown file %s", file_path)
        return {}, ""


def find_markdown_files(directory: str, site_filter: str | None = None) -> list[str]:
    """Find all markdown files in a directory, optionally filtering by site.

    Args:
        directory: Directory to search for markdown files
        site_filter: Optional site name to filter by (e.g. 'migri')

    Returns:
        List of paths to markdown files
    """
    markdown_files = []

    try:
        for file_path_obj in Path(directory).rglob("*.md"):
            file_path = str(file_path_obj)

            # Apply site filter if specified
            if site_filter:
                # Check if the file is in the specified site's directory
                try:
                    # Get relative path of the containing directory from the base directory
                    relative_path = file_path_obj.parent.relative_to(directory)
                    path_parts = relative_path.parts

                    # Check if the first part of the path is the site name
                    if len(path_parts) > 0 and path_parts[0] == site_filter:
                        markdown_files.append(file_path)
                except ValueError, IndexError:
                    # Skip files that don't match the site structure
                    pass
            else:
                markdown_files.append(file_path)
    except Exception:
        logger.exception("Error finding markdown files")

    return markdown_files
