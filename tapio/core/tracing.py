"""LangSmith tracing setup for the Tapio application.

Provides a ``setup_langsmith`` function that configures LangSmith tracing
from environment variables (or a ``.env`` file).  Tracing is a no-op when
no LangSmith API key is configured, so it is safe to call unconditionally.
"""

import logging
import os

from dotenv import load_dotenv

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
