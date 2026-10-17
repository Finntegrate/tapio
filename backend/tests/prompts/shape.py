"""Shared assertion helper for prompts that embed a ``render_json_shape`` line."""

import re

_SHAPE_LINE = re.compile(r"^\{.*\}$", re.MULTILINE)
_FIELD_NAME = re.compile(r'"(\w+)": <')


def shape_field_names(prompt: str) -> set[str]:
    """Return the field names in the single JSON shape line ``prompt`` shows the model.

    Args:
        prompt: A rendered prompt containing exactly one ``{...}`` shape line.

    Returns:
        The field names that shape line asks the model for.
    """
    lines = _SHAPE_LINE.findall(prompt)
    assert len(lines) == 1, f"expected exactly one JSON shape line, found {lines!r}"
    return set(_FIELD_NAME.findall(lines[0]))
