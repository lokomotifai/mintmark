"""Turkish base lexicons and the real-institution denylist.

`import-linter` holds this package to importing only `engine`. The denylist
scanner needs Turkish folding, which lives in `engine` precisely so that both
this package and `identifiers` can reach it without either depending on the
other.
"""

from __future__ import annotations

from mintmark.lexicons.denylist import Denylist, DenylistHit, load, parse

__all__ = ["Denylist", "DenylistHit", "load", "parse"]
