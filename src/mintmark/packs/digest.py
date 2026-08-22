"""The canonical pack digest.

A manifest records which pack produced a dataset. A name and a version are not
enough: two builds of the same version can differ, and a consumer verifying a
published dataset needs to know it is holding the same declarations that minted
it. The digest is that binding.

    for each declarative file, sorted bytewise by relative POSIX path:
        <path> 0x00 <lowercase hex sha256 of content> 0x0A
    digest = sha256(concatenation)

Declarative means the files the loader reads: `pack.yaml`, and everything under
`fields/`, `recipes/`, `templates/`, `lexicons/`, and `assets/`. Nothing else.
The reasoning for that boundary, and the three ways the earlier one failed, are
in the comment above the allowlist.

Committed samples are output rather than declaration, so they sit outside it and
a sample refresh leaves the digest alone.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# The digest covers what the loader reads and nothing else.
#
# It used to cover the whole pack directory minus a short denylist, which meant
# it covered README files, the changelog, the test suite, the lockfile, the
# vendored engine wheel, compiled `__pycache__` output, and `PLAN.md` — a file
# some packs deliberately keep out of git. Three consequences, all observed:
# a clean clone and a working checkout of the same commit produced different
# digests; running the suite under a different pytest version changed the digest
# through the `.pyc` files; and editing documentation changed the digest of a
# pack whose declarations had not moved.
#
# A digest that behaves that way cannot do the job it exists for. It is supposed
# to bind a dataset to the declarations that produced it, so that somebody
# holding the dataset can tell whether a pack they have is the pack it came from.
# Binding it to a README answers a different question nobody asked.
#
# An allowlist rather than a denylist, because the failure modes above were all
# things nobody thought to deny. A pack that grows a new declarative directory
# has to be added here, and that friction is correct for something a published
# manifest depends on.
DECLARATIVE_FILES = frozenset({"pack.yaml"})
DECLARATIVE_DIRECTORIES = frozenset({"fields", "recipes", "templates", "lexicons", "assets"})


def enumerate_files(pack_root: Path) -> list[Path]:
    """Every file the digest covers, sorted bytewise by relative POSIX path."""
    candidates: list[tuple[bytes, Path]] = []
    for path in pack_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(pack_root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        first = relative.parts[0]
        declarative = (
            first in DECLARATIVE_FILES
            if len(relative.parts) == 1
            else first in DECLARATIVE_DIRECTORIES
        )
        if not declarative:
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
