"""SHA256SUMS: the checksum file a consumer can verify with standard tools.

The format is the one `sha256sum -c` reads, so verification does not require this
project to be installed. That matters for a published dataset: the point of
shipping checksums is that someone who distrusts the generator can still check
the artifacts.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

SUMS_FILENAME = "SHA256SUMS"
_SEPARATOR = "  "


def file_digest(path: Path) -> str:
    """SHA-256 of a file, lowercase hex, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_sums(entries: dict[str, str]) -> str:
    """`sha256  path` per line, sorted bytewise by path, LF terminated."""
    lines = [
        f"{entries[path]}{_SEPARATOR}{path}"
        for path in sorted(entries, key=lambda p: p.encode("utf-8"))
    ]
    return "\n".join(lines) + "\n" if lines else ""


def parse_sums(text: str) -> dict[str, str]:
    """Read a SHA256SUMS file into path-to-digest."""
    entries: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        digest, separator, path = line.partition(_SEPARATOR)
        if not separator or len(digest) != 64:
            raise ValueError(f"{SUMS_FILENAME} line {number} is malformed: {raw!r}")
        entries[path.strip()] = digest
    return entries
