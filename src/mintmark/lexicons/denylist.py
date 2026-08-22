"""Real-institution denylist scanning.

Every fictional bank, insurer, and employer name this project generates is
checked against a list of real institutions before it can ship. The check runs in
required CI over lexicons, templates, and golden outputs, and a hit fails the
build naming both the offending entry and the institution it collided with.

Matching is folded and word-boundary aware, not raw substring. Raw substring
matching would be both too weak and too strong: too weak because "Akbank" and
"AKBANK T.A.Ş." do not contain each other, and too strong because an entry like
"hayat" would fire on every Turkish sentence using the ordinary word for life.

The denylist file itself carries the qualification that keeps entries
unambiguous; this module carries the matching discipline that makes them usable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from mintmark.engine.fold import fold


@dataclass(frozen=True, slots=True)
class DenylistHit:
    """One collision between generated content and a real institution."""

    surface: str
    entry: str
    source: str

    def render(self) -> str:
        return (
            f"{self.surface!r} collides with denylist entry {self.entry!r} "
            f"(real institution: {self.source})"
        )


@dataclass(frozen=True, slots=True)
class Denylist:
    """A loaded denylist: folded phrases with the institution each came from."""

    entries: dict[str, str]

    def __len__(self) -> int:
        return len(self.entries)

    def scan(self, text: str) -> list[DenylistHit]:
        """Return every entry that appears in `text` as a whole phrase."""
        folded = fold(text)
        hits: list[DenylistHit] = []
        for entry, source in self.entries.items():
            # \b on both ends so "ing" matches the bank but not "brifing".
            if re.search(rf"\b{re.escape(entry)}\b", folded):
                hits.append(DenylistHit(surface=text, entry=entry, source=source))
        return hits

    def scan_all(self, surfaces: list[str]) -> list[DenylistHit]:
        return [hit for surface in surfaces for hit in self.scan(surface)]

    def covers(self, other: Denylist) -> bool:
        """Return True when this list is a superset of `other`.

        A pack may extend the core denylist and may never shrink it, so a pack's
        list has to cover the core's entry for entry.
        """
        return set(other.entries) <= set(self.entries)

    def missing_from(self, other: Denylist) -> set[str]:
        return set(other.entries) - set(self.entries)


def parse(text: str) -> Denylist:
    """Parse a denylist file: one phrase per line, optional trailing comment."""
    entries: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        phrase, _, comment = line.partition("#")
        phrase = phrase.strip()
        if not phrase:
            continue
        if len(phrase) < 3:
            raise ValueError(
                f"denylist entry {phrase!r} is shorter than three characters. Short "
                "entries match too much; qualify it with more of the institution name."
            )
        entries[fold(phrase)] = comment.strip() or phrase
    if not entries:
        raise ValueError("denylist is empty; an empty denylist silently permits everything")
    return Denylist(entries=entries)


def load(path: Path) -> Denylist:
    """Load a denylist from disk."""
    if not path.exists():
        raise FileNotFoundError(f"no denylist at {path}")
    return parse(path.read_text(encoding="utf-8"))
