"""Parse numeric claim quantities into value + unit."""

from __future__ import annotations

import re

_QUANTITY_RE = re.compile(
    r"""
    ^\s*
    (?P<value>
        [+-]?
        (?:
            (?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?
        )
    )
    \s*
    (?P<unit>\S+)?
    \s*$
    """,
    re.VERBOSE,
)


def parse_quantity(text: str | float | int | None) -> tuple[float | None, str | None]:
    """Split a quantity string into ``(object_value, unit)``.

    Examples:
        ``"1%"`` → ``(1.0, "%")``
        ``"0.01"`` / ``"1e-2"`` → ``(0.01, None)``
    """

    if text is None:
        return None, None
    if isinstance(text, bool):
        return None, None
    if isinstance(text, (int, float)):
        return float(text), None

    raw = str(text).strip()
    if not raw:
        return None, None

    match = _QUANTITY_RE.match(raw)
    if match is None:
        return None, None

    value = float(match.group("value"))
    unit = match.group("unit")
    return value, unit
