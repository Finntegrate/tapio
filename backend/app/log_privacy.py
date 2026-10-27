"""Keep conversation content out of logs and away from third-party tracing (#191, ADR 0011).

Three guards, all installed by ``app.main.create_app`` before anything else runs:

- ``refuse_third_party_tracing``: LangChain's tracing client ships as a dependency, and
  one environment variable would send every prompt to LangSmith. The service refuses to
  start with tracing switched on, or with a tracing key or endpoint configured.
- ``install_content_free_exception_logging``: an exception's message is where user text
  leaks into logs - a provider error quoting the prompt, a validation error quoting the
  rejected value. Every log record carrying an exception is rewritten to keep only the
  exception's type and where it was raised (file, line, function), never its message or
  any value involved. Explicit log calls must follow the same rule: name a category, a
  count, or a type, never a message, reason, or model output.
- ``quiet_content_logging_libraries``: some dependencies log conversation content
  themselves at DEBUG - every streamed SSE chunk, every provider request body - so
  they are held at INFO even when the rest of the app logs at DEBUG.
"""

import logging
import os
import traceback
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Final

# Env vars that switch LangChain/LangSmith tracing on. Any truthy value refuses start-up.
TRACING_FLAGS: Final[tuple[str, ...]] = (
    "LANGSMITH_TRACING",
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING",
    "LANGCHAIN_TRACING_V2",
)

# Env vars that point LangSmith at an account or server. Any value at all refuses start-up:
# set, they make enabling tracing a one-flag change away.
TRACING_TARGETS: Final[tuple[str, ...]] = (
    "LANGSMITH_API_KEY",
    "LANGCHAIN_API_KEY",
    "LANGSMITH_ENDPOINT",
    "LANGCHAIN_ENDPOINT",
)

_FALSY: Final = frozenset({"", "0", "false", "no", "off"})

# Loggers that write conversation content at DEBUG: sse_starlette logs every chunk it
# streams (model replies, guardrail reasons); the openai and anthropic clients log each
# request's options, including the messages sent.
CONTENT_LOGGING_LIBRARIES: Final[tuple[str, ...]] = ("sse_starlette", "openai", "anthropic")

# How many innermost frames an exception's location keeps.
_MAX_FRAMES: Final = 8


class ThirdPartyTracingError(RuntimeError):
    """Raised at start-up when third-party tracing is enabled or configured."""


def refuse_third_party_tracing(environ: Mapping[str, str] | None = None) -> None:
    """Refuse to start if LangChain/LangSmith tracing is enabled or configured.

    Args:
        environ: The environment to check; defaults to ``os.environ``.

    Raises:
        ThirdPartyTracingError: Naming each offending variable, never its value.
    """
    env = os.environ if environ is None else environ
    offending = [name for name in TRACING_FLAGS if env.get(name, "").strip().lower() not in _FALSY]
    offending += [name for name in TRACING_TARGETS if env.get(name, "").strip()]
    if offending:
        msg = (
            f"Refusing to start: third-party tracing would send conversation content off-site "
            f"(ADR 0011). Unset {', '.join(offending)}."
        )
        raise ThirdPartyTracingError(msg)


def describe_exception(error: BaseException) -> str:
    """Describe ``error`` by type and location only, for a log line.

    Args:
        error: The exception being logged.

    Returns:
        E.g. ``"ValueError at app/graph/nodes.py:131 in generate <- ..."``, followed by the
        same for each exception it was raised from. Never the message.
    """
    parts = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(f"{type(current).__qualname__} at {_location(current.__traceback__)}")
        current = current.__cause__ or current.__context__
    return "\nraised from: ".join(parts)


def _location(tb: TracebackType | None) -> str:
    frames = traceback.extract_tb(tb)[-_MAX_FRAMES:]
    if not frames:
        return "<unknown>"
    return " <- ".join(f"{_short_path(frame.filename)}:{frame.lineno} in {frame.name}" for frame in reversed(frames))


def _short_path(filename: str) -> str:
    normalized = filename.replace("\\", "/")
    for marker in ("/site-packages/", "/backend/"):
        if marker in normalized:
            return normalized.split(marker, 1)[1]
    return normalized.rsplit("/", 1)[-1]


_installed = False


def install_content_free_exception_logging() -> None:
    """Rewrite every log record's exception to its type and location, process-wide.

    Wraps the logging record factory, so it covers every logger (this app's and its
    dependencies') and every handler, however logging is configured later. Idempotent.
    """
    global _installed  # noqa: PLW0603 - installed once per process
    if _installed:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = previous(*args, **kwargs)
        if record.exc_info and record.exc_info[1] is not None:
            record.exc_text = describe_exception(record.exc_info[1])
            record.exc_info = None
        return record

    logging.setLogRecordFactory(factory)
    _installed = True


def quiet_content_logging_libraries() -> None:
    """Hold the libraries that log conversation content at DEBUG to INFO and above.

    Always sets an explicit level: a logger left at NOTSET inherits from the root, so a
    later switch of the root to DEBUG would let it log content again.
    """
    for name in CONTENT_LOGGING_LIBRARIES:
        logger = logging.getLogger(name)
        logger.setLevel(max(logger.getEffectiveLevel(), logging.INFO))
