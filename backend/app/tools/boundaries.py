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

from collections.abc import Iterator, Mapping
from functools import partial
from types import FunctionType, MethodType, ModuleType
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
    """Yield every value a tool's code can reach without importing anything new.

    Starts from the tool's own fields and, for its function (and coroutine), the closure
    cells, default arguments, and bound ``self``, then walks into containers, object
    fields, and nested functions, so a store wrapped in a list or another object is still
    found. Each object is visited once (cycles are safe), and the walk stops at
    ``_MAX_DEPTH`` levels. A module-level global isn't covered: a store held that way is
    shared process state, which the stores themselves must not expose.
    """
    roots: list[Any] = [*vars(tool).values()]
    for function in (getattr(tool, "func", None), getattr(tool, "coroutine", None)):
        if function is not None:
            roots.extend(_function_values(function))

    seen: set[int] = set()
    stack = [(value, 0) for value in roots]
    while stack:
        value, depth = stack.pop()
        if id(value) in seen or isinstance(value, _LEAF_TYPES):
            continue
        seen.add(id(value))
        yield value
        if depth < _MAX_DEPTH:
            stack.extend((child, depth + 1) for child in _children(value))


# Values that can't hold a handle, or whose contents are code rather than state.
_LEAF_TYPES: Final = (str, bytes, int, float, complex, bool, type(None), type, ModuleType)

# Deep enough for a store inside a wrapper inside a container; bounded so a tool holding
# e.g. a chat model doesn't walk that model's whole client graph.
_MAX_DEPTH: Final = 6


def _function_values(function: Any) -> Iterator[Any]:
    """Yield what a function closes over: bound ``self``, closure cells, and defaults."""
    yield getattr(function, "__self__", None)
    for cell in getattr(function, "__closure__", None) or ():
        try:
            yield cell.cell_contents
        except ValueError:  # an empty cell, for a variable not yet assigned
            continue
    yield from getattr(function, "__defaults__", None) or ()
    yield from (getattr(function, "__kwdefaults__", None) or {}).values()


def _children(value: Any) -> Iterator[Any]:
    """Yield the values directly inside ``value``: container items, fields, or a function's captures."""
    if isinstance(value, Mapping):
        yield from value.keys()
        yield from value.values()
    elif isinstance(value, (list, tuple, set, frozenset)):
        yield from value
    elif isinstance(value, FunctionType | MethodType | partial):
        yield from _function_values(getattr(value, "func", value))
        yield from getattr(value, "args", ())
        yield from (getattr(value, "keywords", None) or {}).values()
    else:
        yield from (getattr(value, "__dict__", None) or {}).values()
        for slot in getattr(type(value), "__slots__", ()):
            if hasattr(value, slot):
                yield getattr(value, slot)
