"""Allow ``python -m mintmark`` to reach the same entry point as the console script."""

from __future__ import annotations

from mintmark.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
