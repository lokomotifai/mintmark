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
import os
import stat
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
MAX_PACK_FILES = 4_096
MAX_PACK_FILE_BYTES = 64 << 20
MAX_PACK_TOTAL_BYTES = 256 << 20
_CHUNK_BYTES = 1 << 20


class PackDigestError(ValueError):
    """A pack tree cannot be safely and deterministically digested."""


def _root_metadata(pack_root: Path) -> os.stat_result:
    try:
        metadata = pack_root.lstat()
    except OSError as exc:
        raise NotADirectoryError(f"not a pack directory: {pack_root}") from exc
    if pack_root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise NotADirectoryError(f"not a regular pack directory: {pack_root}")
    return metadata


def enumerate_files(pack_root: Path) -> list[Path]:
    """Every file the digest covers, sorted bytewise by relative POSIX path."""
    pack_root = Path(pack_root)
    _root_metadata(pack_root)
    candidates: list[tuple[bytes, Path]] = []
    for path in pack_root.rglob("*"):
        relative = path.relative_to(pack_root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        first = relative.parts[0]
        declarative = (
            first in DECLARATIVE_FILES or first in DECLARATIVE_DIRECTORIES
            if len(relative.parts) == 1
            else first in DECLARATIVE_DIRECTORIES
        )
        if not declarative:
            continue
        try:
            metadata = path.lstat()
        except OSError as exc:
            raise PackDigestError(f"cannot inspect pack path {relative.as_posix()}: {exc}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise PackDigestError(f"pack path {relative.as_posix()} is a symbolic link")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise PackDigestError(f"pack path {relative.as_posix()} is not a regular file")
        candidates.append((relative.as_posix().encode("utf-8"), path))
        if len(candidates) > MAX_PACK_FILES:
            raise PackDigestError(f"pack contains more than {MAX_PACK_FILES} declarative files")
    candidates.sort(key=lambda item: item[0])
    return [path for _, path in candidates]


def _stable_file_digest(path: Path) -> tuple[str, int]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise PackDigestError(f"cannot open pack file {path}: {exc}") from exc
    digest = hashlib.sha256()
    read_bytes = 0
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise PackDigestError(f"pack path {path} is not a regular file")
        if before.st_size > MAX_PACK_FILE_BYTES:
            raise PackDigestError(
                f"pack file {path} is {before.st_size} bytes; maximum is {MAX_PACK_FILE_BYTES}"
            )
        while True:
            chunk = os.read(descriptor, _CHUNK_BYTES)
            if not chunk:
                break
            read_bytes += len(chunk)
            if read_bytes > MAX_PACK_FILE_BYTES:
                raise PackDigestError(
                    f"pack file {path} exceeds the {MAX_PACK_FILE_BYTES}-byte limit"
                )
            digest.update(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after or read_bytes != after.st_size:
        raise PackDigestError(f"pack file {path} changed while it was being hashed")
    return digest.hexdigest(), read_bytes


def canonical_lines(pack_root: Path) -> bytes:
    """The exact byte sequence the digest is taken over."""
    chunks: list[bytes] = []
    total_bytes = 0
    for path in enumerate_files(pack_root):
        relative = path.relative_to(pack_root).as_posix().encode("utf-8")
        digest, size = _stable_file_digest(path)
        total_bytes += size
        if total_bytes > MAX_PACK_TOTAL_BYTES:
            raise PackDigestError(
                f"pack declarative bytes exceed the {MAX_PACK_TOTAL_BYTES}-byte aggregate limit"
            )
        content = digest.encode("ascii")
        chunks.append(relative + b"\x00" + content + b"\x0a")
    return b"".join(chunks)


def pack_digest(pack_root: Path) -> str:
    """SHA-256 over the canonical enumeration, lowercase hex."""
    _root_metadata(Path(pack_root))
    return hashlib.sha256(canonical_lines(pack_root)).hexdigest()
