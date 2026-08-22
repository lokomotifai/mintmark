"""The library surface: two functions, mirroring the CLI's --json payloads.

Kept this small on purpose. Everything the CLI can do is reachable, and nothing
else is promised, so the compatibility surface stays something a maintainer can
hold in mind.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mintmark.annotate import pin_digest
from mintmark.identifiers import CHECKSUMMED
from mintmark.manifest import VerifyReport
from mintmark.manifest import verify as _verify
from mintmark.mint import schema_dir

__all__ = ["verify"]


def verify(directory: str | Path) -> VerifyReport:
    """Revalidate a dataset against its manifest, recomputing every claim."""
    schema: dict[str, Any] = json.loads(
        (schema_dir() / "manifest.schema.json").read_text(encoding="utf-8")
    )
    validators = {name: engine.is_checksum_valid for name, engine in CHECKSUMMED.items()}
    return _verify(
        Path(directory),
        schema=schema,
        validators=validators,
        expected_taxonomy_pin=pin_digest(),
    )
