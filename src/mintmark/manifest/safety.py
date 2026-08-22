"""Checksum-bearing identifier candidates in emitted scalar values."""

from __future__ import annotations

import re
from collections.abc import Iterable

# Accept compact and arbitrarily space-grouped Turkish IBANs.  Validators perform
# the final shape/checksum decision; this expression only finds bounded candidates.
_CANDIDATE = re.compile(
    r"(?<![0-9A-Za-z])(?:TR[0-9]{2}(?: ?[0-9]){22}|[0-9]{10,19})(?![0-9A-Za-z])"
)


def scalar_texts(value: object) -> Iterable[str]:
    """Yield every textual or integer scalar a dataset consumer can observe."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, int) and not isinstance(value, bool):
        yield str(value)
    elif isinstance(value, dict):
        for item in value.values():
            yield from scalar_texts(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from scalar_texts(item)


def identifier_candidates(value: object) -> Iterable[str]:
    """Yield normalized, de-duplicated candidates from nested scalar values."""
    seen: set[str] = set()
    for text in scalar_texts(value):
        for match in _CANDIDATE.finditer(text):
            candidate = match.group().replace(" ", "")
            if candidate not in seen:
                seen.add(candidate)
                yield candidate
