"""What a registered tool must never be able to reach (ADR 0011, privacy and security baseline).

The model is untrusted: its input includes user messages and crawled pages, so any
instruction in them may be followed. Isolation therefore can't rest on the prompt;
it rests on what a tool can reach. ``check_tool_boundaries`` is run on every tool at
registration and rejects one that could reach another person's data:

- an argument naming a conversation, session, account, or thread, which would let
  the model choose whose data to read;
- a handle to a ``RestrictedResource`` (the identity, checkpoint, and secret stores,
  and the operator command), found in the tool's own fields, its function's
  closure, or its default arguments;
- a tool not declared read-only.
"""

from collections.abc import Iterator
from typing import Any, Final

from langchain_core.tools import BaseTool

# Any argument whose name contains one of these lets the model pick whose data a call touches.
FORBIDDEN_ARGUMENT_PARTS: Final[tuple[str, ...]] = ("conversation", "session", "account", "thread")


class RestrictedResource:
    """Marker base for a handle no tool may hold.

    The identity store, checkpoint store, secret store, and operator command subclass
    this when they are built, so a tool closing over one fails at registration rather
    than in review.
    """


def check_tool_boundaries(tool: BaseTool, *, read_only: bool) -> None:
    """Reject a tool that could reach beyond the caller's own turn.

    Args:
        tool: The tool being registered.
        read_only: Whether the tool's author declared it free of side effects.

    Raises:
        ValueError: If the tool takes an identifying argument, holds a restricted
            handle, or isn't read-only.
    """
    if not read_only:
        msg = f"Tool {tool.name!r} is not read-only; registered tools must be read-only"
        raise ValueError(msg)

    identifying = sorted(name for name in tool.args if any(part in name.lower() for part in FORBIDDEN_ARGUMENT_PARTS))
    if identifying:
        msg = f"Tool {tool.name!r} takes identifying arguments {identifying}; no tool may choose whose data it reads"
        raise ValueError(msg)

    restricted = sorted(
        {type(value).__name__ for value in _reachable_values(tool) if isinstance(value, RestrictedResource)}
    )
    if restricted:
        msg = f"Tool {tool.name!r} holds restricted handles {restricted}"
        raise ValueError(msg)


def _reachable_values(tool: BaseTool) -> Iterator[Any]:
    """Yield the values a tool's code can reach without importing anything new.

    Covers the tool's own fields and, for its function (and coroutine), the closure cells,
    default arguments, and bound ``self``. A module-level global isn't covered: a store
    held that way is shared process state, which the stores themselves must not expose.
    """
    yield from vars(tool).values()
    for function in (getattr(tool, "func", None), getattr(tool, "coroutine", None)):
        if function is None:
            continue
        yield getattr(function, "__self__", None)
        yield from (cell.cell_contents for cell in getattr(function, "__closure__", None) or ())
        yield from getattr(function, "__defaults__", None) or ()
        yield from (getattr(function, "__kwdefaults__", None) or {}).values()
