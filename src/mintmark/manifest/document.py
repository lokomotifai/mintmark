"""MINTMARK.json: the record that makes a directory of files a dataset.

A directory of JSONL files is data. A directory of JSONL files with a manifest is
evidence: it says which engine produced it, from which pack at which digest,
under which recipe, seed, and identifier policy, against which taxonomy pin, and
what the resulting distributions actually were. Anyone holding the artifacts can
re-derive the data and compare.

The `provenance` block is excluded from the byte-level determinism claim, because
it records when the mint ran and how it was invoked. Everything else is included,
which is what makes `reproduce` a real check rather than a comparison of the
parts nobody disputes.

The validator warning is present if and only if the policy is `validator`. The
schema encodes that as a conditional, so a validator dataset with the warning
stripped fails validation rather than passing quietly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "MINTMARK.json"
SCHEMA_VERSION = 1

# Fixed text, defined once so that the writer and the verifier cannot drift.
VALIDATOR_WARNING = (
    'This dataset was minted with identifier policy "validator". It contains '
    "checksum-valid synthetic identifiers intended solely for testing validation "
    "logic. The values are fictional and belong to no real person, account, or "
    "institution. Do not use this dataset where checksum-valid identifiers could "
    "be mistaken for real ones."
)

DETERMINISM_CLAIM = (
    "Byte-identical data files and label sidecars for identical engine version, "
    "pack digest, recipe, seed, identifier policy, and output format."
)

SUPPORTED_PLATFORMS: tuple[str, ...] = (
    "CPython 3.12 on Linux x86_64",
    "CPython 3.12 on Linux arm64",
    "CPython 3.12 on macOS arm64",
)

EXCLUDED_FROM_CLAIM: tuple[str, ...] = ("provenance.created_utc", "provenance.invocation")


@dataclass(frozen=True, slots=True)
class OutputFile:
    """One emitted file, with the checksum that binds it to this manifest."""

    path: str
    bytes: int
    sha256: str
    records: int

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "records": self.records,
        }


@dataclass(frozen=True, slots=True)
class DistributionStat:
    site: str
    target: dict[str, str]
    achieved: dict[str, str]
    within_tolerance: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "target": self.target,
            "achieved": self.achieved,
            "within_tolerance": self.within_tolerance,
        }


@dataclass(frozen=True, slots=True)
class CoverageStat:
    """A declared coverage target against what the mint actually produced.

    Recorded whether or not it was met. A target that was missed is a fact about
    the dataset, and hiding it would make an evaluation set silently weaker than
    the recipe promised.
    """

    label: str
    target: int
    achieved: int

    @property
    def met(self) -> bool:
        return self.achieved >= self.target

    def to_json(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "target": self.target,
            "achieved": self.achieved,
            "met": self.met,
        }


@dataclass(frozen=True, slots=True)
class Manifest:
    """The whole record, assembled once at the end of a mint."""

    engine_version: str
    pack_name: str
    pack_version: str
    pack_digest: str
    recipe_name: str
    records: dict[str, int]
    date_window: tuple[str, str]
    seed: int
    identifier_policy: str
    taxonomy: dict[str, str]
    outputs: tuple[OutputFile, ...]
    distributions: tuple[DistributionStat, ...]
    coverage: tuple[CoverageStat, ...]
    entity_coverage: dict[str, int]
    created_utc: str
    invocation: str
    overrides: dict[str, Any] = dataclass_field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        document: dict[str, Any] = {
            "mintmark": {
                "engine_version": self.engine_version,
                "manifest_schema_version": SCHEMA_VERSION,
            },
            "pack": {
                "name": self.pack_name,
                "version": self.pack_version,
                "digest": self.pack_digest,
            },
            "recipe": {
                "name": self.recipe_name,
                "parameters": {
                    "records": dict(sorted(self.records.items())),
                    "date_window": {"start": self.date_window[0], "end": self.date_window[1]},
                    "overrides": dict(sorted(self.overrides.items())),
                },
            },
            "seed": str(self.seed),
            "identifier_policy": self.identifier_policy,
        }
        if self.identifier_policy == "validator":
            document["validator_warning"] = VALIDATOR_WARNING

        document["taxonomy"] = dict(self.taxonomy)
        document["outputs"] = [output.to_json() for output in self.outputs]
        document["stats"] = {
            "record_counts": dict(sorted(self.records.items())),
            "distributions": [stat.to_json() for stat in self.distributions],
            "coverage_targets": [stat.to_json() for stat in self.coverage],
        }
        document["entity_coverage"] = dict(sorted(self.entity_coverage.items()))
        document["determinism"] = {
            "claim": DETERMINISM_CLAIM,
            "platforms": list(SUPPORTED_PLATFORMS),
            "excluded": list(EXCLUDED_FROM_CLAIM),
        }
        document["provenance"] = {
            "created_utc": self.created_utc,
            "invocation": self.invocation,
        }
        return document

    def render(self) -> str:
        """The manifest as it is written: indented, LF, trailing newline.

        Indented rather than compact because a human reads this file, and a
        consumer diffing two manifests wants line-level differences.
        """
        return json.dumps(self.to_json(), ensure_ascii=False, indent=2) + "\n"


def comparable(document: dict[str, Any]) -> dict[str, Any]:
    """The manifest with the fields the determinism claim excludes removed.

    Used by `reproduce`. Comparing whole manifests would fail on the timestamp
    every time, which would either make the check useless or teach people to
    ignore it.
    """
    stripped = json.loads(json.dumps(document))
    stripped.pop("provenance", None)
    return dict(stripped)


def read_manifest(directory: Path) -> dict[str, Any]:
    path = Path(directory) / MANIFEST_FILENAME
    if not path.exists():
        raise FileNotFoundError(
            f"no {MANIFEST_FILENAME} in {directory}. A dataset without its manifest "
            "is not a Mintmark deliverable: nothing binds the files to what produced them."
        )
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document
