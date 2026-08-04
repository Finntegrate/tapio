"""Filesystem and network defaults owned by the crawler service."""

import os

# An external volume can supply this path; local development uses the
# monorepo's adjacent ``content/`` directory by default.
DEFAULT_CONTENT_DIR = os.environ.get("TAPIO_CONTENT_DIR", "../content")
# Crawl4AI stores its reusable HTTP cache in ``{base}/.crawl4ai``. Keep it on
# the same persistent volume as collected Markdown unless deployment overrides
# ``CRAWL4_AI_BASE_DIRECTORY``.
DEFAULT_CRAWL4AI_BASE_DIRECTORY = DEFAULT_CONTENT_DIR
# SQLite-backed URL manifest (see docs/specs/crawler-improvements.md). Shared
# across sites, one row per (site_name, canonical_url).
DEFAULT_MANIFEST_PATH = os.environ.get(
    "TAPIO_MANIFEST_PATH",
    os.path.join(DEFAULT_CONTENT_DIR, "manifest.db"),
)

# Default directory paths. Crawl4AI writes directly to parsed Markdown.
DEFAULT_DIRS = {
    "PARSED_DIR": "parsed",
}
