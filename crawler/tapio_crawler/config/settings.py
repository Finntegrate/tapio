"""Filesystem and network defaults owned by the crawler service."""

import os

# An external volume can supply this path; local development uses the
# monorepo's adjacent ``content/`` directory by default.
DEFAULT_CONTENT_DIR = os.environ.get("TAPIO_CONTENT_DIR", "../content")
# Crawl4AI stores its reusable HTTP cache in ``{base}/.crawl4ai``. Keep it on
# the same persistent volume as collected Markdown unless deployment overrides
# ``CRAWL4_AI_BASE_DIRECTORY``.
DEFAULT_CRAWL4AI_BASE_DIRECTORY = DEFAULT_CONTENT_DIR

# Default directory paths. Crawl4AI writes directly to parsed Markdown.
DEFAULT_DIRS = {
    "PARSED_DIR": "parsed",
}
