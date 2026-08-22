"""The canonical pack digest.

A manifest records which pack produced a dataset. A name and a version are not
enough: two builds of the same version can differ, and a consumer verifying a
published dataset needs to know it is holding the same declarations that minted
it. The digest is that binding.

    for each file outside datasets/ and samples/, sorted bytewise by POSIX path:
        <path> 0x00 <lowercase hex sha256 of content> 0x0A
    digest = sha256(concatenation)

Excluding `datasets/` and `samples/` is what makes the digest stable across a
sample refresh. Samples are committed output, so including them would make the
digest depend on its own product.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

EXCLUDED_DIRECTORIES = frozenset({"datasets", "samples"})
EXCLUDED_NAMES = frozenset({".DS_Store"})


def enumerate_files(pack_root: Path) -> list[Path]:
    """Every file the digest covers, sorted bytewise by relative POSIX path."""
    candidates: list[tuple[bytes, Path]] = []
    for path in pack_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(pack_root)
        if relative.parts and relative.parts[0] in EXCLUDED_DIRECTORIES:
            continue
        if path.name in EXCLUDED_NAMES:
            continue
        if any(part.startswith(".") for part in relative.parts):
            continue
        candidates.append((relative.as_posix().encode("utf-8"), path))
    candidates.sort(key=lambda item: item[0])
    return [path for _, path in candidates]


def canonical_lines(pack_root: Path) -> bytes:
    """The exact byte sequence the digest is taken over."""
    chunks: list[bytes] = []
    for path in enumerate_files(pack_root):
        relative = path.relative_to(pack_root).as_posix().encode("utf-8")
        content = hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii")
        chunks.append(relative + b"\x00" + content + b"\x0a")
    return b"".join(chunks)


def pack_digest(pack_root: Path) -> str:
    """SHA-256 over the canonical enumeration, lowercase hex."""
    if not pack_root.is_dir():
        raise NotADirectoryError(f"not a pack directory: {pack_root}")
    return hashlib.sha256(canonical_lines(pack_root)).hexdigest()
