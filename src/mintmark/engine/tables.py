"""Sampling continuous distributions without a transcendental function.

The mint path may not call `math.log` or `math.exp`, because libm results differ
across platforms and a log-normal amount computed at mint time would produce
different bytes on Linux and macOS for the same seed. All transcendental work
happens offline in `tools/gen_tables.py`, whose output is committed and
checksummed. This module reads that output and interpolates between its knots in
integer arithmetic only.

Interpolation is linear between adjacent knots, computed as

    value = low + (high - low) * offset // divisor

with every term an integer. Floor division is exact and identical on every
platform, which is precisely what a float multiply would not be.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from mintmark.engine.draws import bounded
from mintmark.engine.prng import SplitMix64

# Resolution within one knot interval. A draw picks a knot and then a position
# inside its interval, so the sampler is not restricted to 1024 distinct values.
SUBDIVISIONS = 1 << 20


@dataclass(frozen=True, slots=True)
class Table:
    """A loaded inverse-CDF table.

    `values` is monotonically non-decreasing by construction. That property is
    checked at load time rather than assumed, because a table that lost its
    ordering would silently produce a distribution nobody declared.
    """

    name: str
    unit: str
    values: tuple[int, ...]
    digest: str

    def __post_init__(self) -> None:
        if len(self.values) < 2:
            raise ValueError(f"table {self.name!r} needs at least two knots")
        for index in range(len(self.values) - 1):
            if self.values[index] > self.values[index + 1]:
                raise ValueError(
                    f"table {self.name!r} is not monotonic at knot {index}: "
                    f"{self.values[index]} then {self.values[index + 1]}"
                )

    @property
    def minimum(self) -> int:
        return self.values[0]

    @property
    def maximum(self) -> int:
        return self.values[-1]


class TableError(Exception):
    """A table is missing, unreadable, or does not match its recorded checksum."""


def load_table(directory: Path, name: str) -> Table:
    """Load one table and verify it against the directory's CHECKSUMS file.

    A checksum mismatch refuses the load rather than warning. A table is part of
    the determinism contract: sampling from an altered one would produce values
    that no published manifest can reproduce, and doing so quietly is worse than
    not sampling at all.
    """
    path = directory / f"{name}.json"
    if not path.exists():
        raise TableError(
            f"no table named {name!r} in {directory}. A pack declaring an unknown "
            "table is a missing table, which is a core change rather than a pack "
            "workaround."
        )

    raw = path.read_text(encoding="utf-8")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    _verify_checksum(directory, name, digest)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TableError(f"table {name!r} is not valid JSON: {exc}") from exc

    try:
        values = tuple(int(v) for v in payload["values"])
        unit = str(payload["unit"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TableError(f"table {name!r} is malformed: {exc}") from exc

    return Table(name=name, unit=unit, values=values, digest=digest)


def _verify_checksum(directory: Path, name: str, digest: str) -> None:
    checksums = directory / "CHECKSUMS"
    if not checksums.exists():
        raise TableError(f"no CHECKSUMS file in {directory}; tables cannot be trusted without it")

    expected: dict[str, str] = {}
    for line in checksums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        recorded, _, filename = line.partition("  ")
        expected[filename.strip()] = recorded.strip()

    filename = f"{name}.json"
    if filename not in expected:
        raise TableError(f"{filename} is not listed in {checksums}")
    if expected[filename] != digest:
        raise TableError(
            f"table {name!r} does not match its recorded checksum.\n"
            f"  recorded {expected[filename]}\n  actual   {digest}\n"
            "Regenerate with tools/gen_tables.py rather than editing a table by hand."
        )


def sample(stream: SplitMix64, table: Table) -> int:
    """Draw one value from the distribution the table encodes.

    Two integer draws: one selects a knot interval, the other a position inside
    it. The second draw is what stops the sampler from being restricted to the
    1024 committed knots, and it costs one extra u64 per sample.
    """
    intervals = len(table.values) - 1
    index = bounded(stream, intervals)
    offset = bounded(stream, SUBDIVISIONS)

    low = table.values[index]
    high = table.values[index + 1]
    # Integer-only linear interpolation. Floor division is exact and platform
    # independent; a float multiply here would not be.
    return low + (high - low) * offset // SUBDIVISIONS
