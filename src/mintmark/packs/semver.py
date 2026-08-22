"""SemVer range parsing, with a closed upper bound required.

A pack pins the core it was written against. The bound must be closed, because an
open-ended pin means a core released next year could change what a published
manifest reproduces while the pack still claims compatibility. The pack contract
requires the closed bound; this module refuses anything else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RANGE = re.compile(r"^>=(?P<low>\d+\.\d+(?:\.\d+)?),<(?P<high>\d+\.\d+(?:\.\d+)?)$")
_VERSION = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?")


def parse_version(text: str) -> tuple[int, int, int]:
    """Parse a version, ignoring any pre-release or build suffix."""
    match = _VERSION.match(text)
    if match is None:
        raise ValueError(f"not a version: {text!r}")
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch") or 0),
    )


@dataclass(frozen=True, slots=True)
class CoreRange:
    """A closed-upper-bound range, as `requires_core` declares it."""

    low: tuple[int, int, int]
    high: tuple[int, int, int]
    text: str

    def contains(self, version: str) -> bool:
        return self.low <= parse_version(version) < self.high


def parse_range(text: str) -> CoreRange:
    """Parse `requires_core`, refusing an open-ended range."""
    match = _RANGE.match(text.strip())
    if match is None:
        raise ValueError(
            f"requires_core must be a SemVer range with a closed upper bound, "
            f'for example ">=0.1,<0.2". Got {text!r}. An open-ended pin lets a '
            "future core change what a published manifest reproduces."
        )
    low = parse_version(match.group("low"))
    high = parse_version(match.group("high"))
    if high <= low:
        raise ValueError(f"empty range: {text!r}")
    return CoreRange(low=low, high=high, text=text.strip())
