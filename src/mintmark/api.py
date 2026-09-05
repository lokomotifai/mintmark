"""The library surface: two functions, mirroring the CLI's --json payloads.

Kept this small on purpose. Everything the CLI can do is reachable, and nothing
else is promised, so the compatibility surface stays something a maintainer can
hold in mind.

``mint`` wraps the composition root's function with the same pack resolution
the CLI applies, so that ``mintmark.mint`` and ``mintmark.api.mint`` are one
object and the package never touches a submodule whose name collides with the
function.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mintmark.annotate import Label, pin_digest
from mintmark.identifiers import ALL_ENGINES, CHECKSUMMED
from mintmark.manifest import VerifyReport
from mintmark.manifest import verify as _verify
from mintmark.minting import MintSummary, resolve_pack, schema_dir
from mintmark.minting import mint as _mint

__all__ = ["mint", "verify"]


def mint(
    *,
    pack: str | Path,
    recipe: str,
    seed: int,
    out: str | Path,
    identifier_policy: str | None = None,
    fmt: str = "jsonl",
    records: dict[str, int] | None = None,
    invocation: str = "mintmark mint",
) -> MintSummary:
    """Mint a dataset from a pack, a recipe, and a seed.

    `pack` is resolved the way the CLI resolves `--pack`: a path to a pack
    directory wins, and otherwise a bare name such as `example` reaches the
    pack the engine ships. `identifier_policy` left unset means `safe`;
    `validator` has to be asked for by name.
    """
    return _mint(
        pack=resolve_pack(str(pack)),
        recipe=recipe,
        seed=seed,
        out=out,
        identifier_policy=identifier_policy,
        fmt=fmt,
        records=records,
        invocation=invocation,
    )


def verify(directory: str | Path, *, trusted_manifest_sha256: str | None = None) -> VerifyReport:
    """Revalidate a dataset against its manifest, recomputing every claim."""
    schema: dict[str, Any] = json.loads(
        (schema_dir() / "manifest.schema.json").read_text(encoding="utf-8")
    )
    validators = {name: engine.is_checksum_valid for name, engine in CHECKSUMMED.items()}
    shapes = {name: engine.is_well_formed for name, engine in ALL_ENGINES.items()}
    return _verify(
        Path(directory),
        schema=schema,
        validators=validators,
        shapes=shapes,
        expected_taxonomy_pin=pin_digest(),
        known_labels=frozenset(label.value for label in Label),
        trusted_manifest_sha256=trusted_manifest_sha256,
    )
