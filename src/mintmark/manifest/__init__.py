"""Provenance manifests, checksums, verification, and reproduction.

`import-linter` holds this package to importing `emit`, `annotate`, and `engine`.
The identifier validators verification needs are injected by the CLI, which is
the layer that knows about both this package and `identifiers`.
"""

from __future__ import annotations

from mintmark.manifest.document import (
    DETERMINISM_CLAIM,
    EXCLUDED_FROM_CLAIM,
    MANIFEST_FILENAME,
    SCHEMA_VERSION,
    SUPPORTED_PLATFORMS,
    VALIDATOR_WARNING,
    CoverageStat,
    DistributionStat,
    Manifest,
    OutputFile,
    comparable,
    read_manifest,
)
from mintmark.manifest.sums import SUMS_FILENAME, file_digest, parse_sums, render_sums
from mintmark.manifest.verify import VerifyReport, verify

__all__ = [
    "DETERMINISM_CLAIM",
    "EXCLUDED_FROM_CLAIM",
    "MANIFEST_FILENAME",
    "SCHEMA_VERSION",
    "SUMS_FILENAME",
    "SUPPORTED_PLATFORMS",
    "VALIDATOR_WARNING",
    "CoverageStat",
    "DistributionStat",
    "Manifest",
    "OutputFile",
    "VerifyReport",
    "comparable",
    "file_digest",
    "parse_sums",
    "read_manifest",
    "render_sums",
    "verify",
]
