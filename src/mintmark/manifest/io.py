"""Anchored, bounded reads for untrusted dataset directories.

Verification treats a dataset as hostile input.  Keeping the directory open and
opening simple file names relative to that descriptor prevents path traversal,
symlink following, and parent-directory swap races from changing what is read.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

MAX_CONTROL_FILE_BYTES = 4 << 20
MAX_DATA_FILE_BYTES = 256 << 20
MAX_DATASET_ENTRIES = 512

_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}\Z")


class DatasetIOError(ValueError):
    """An unsafe, unstable, or over-budget dataset filesystem operation."""


def validate_filename(name: object) -> str:
    """Return a safe flat dataset file name or fail closed."""
    if not isinstance(name, str) or not _FILENAME.fullmatch(name) or name in {".", ".."}:
        raise DatasetIOError(f"unsafe dataset file name {name!r}")
    return name


@dataclass(frozen=True, slots=True)
class DatasetEntry:
    name: str
    kind: str


class DatasetReader:
    """Read one immutable view of a flat dataset directory."""

    __slots__ = ("_fd", "_identity", "path")

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            self._fd = os.open(self.path, flags)
        except OSError as exc:
            message = f"cannot safely open dataset directory {self.path}: {exc}"
            raise DatasetIOError(message) from exc
        metadata = os.fstat(self._fd)
        if not stat.S_ISDIR(metadata.st_mode):
            os.close(self._fd)
            raise DatasetIOError(f"dataset path is not a directory: {self.path}")
        self._identity = (metadata.st_dev, metadata.st_ino)

    def __enter__(self) -> DatasetReader:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def _open_regular(self, name: str) -> int:
        safe_name = validate_filename(name)
        flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
        )
        try:
            descriptor = os.open(safe_name, flags, dir_fd=self._fd)
        except OSError as exc:
            raise DatasetIOError(f"cannot safely open {safe_name}: {exc}") from exc
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            os.close(descriptor)
            raise DatasetIOError(f"{safe_name}: expected a regular file")
        return descriptor

    @staticmethod
    def _assert_stable(name: str, before: os.stat_result, after: os.stat_result) -> None:
        before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if before_identity != after_identity:
            raise DatasetIOError(f"{name}: file changed while it was being verified")

    def read_bytes(self, name: str, *, max_bytes: int) -> bytes:
        descriptor = self._open_regular(name)
        try:
            before = os.fstat(descriptor)
            if before.st_size > max_bytes:
                raise DatasetIOError(
                    f"{name}: {before.st_size} bytes exceeds the "
                    f"{max_bytes}-byte verification limit"
                )
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining:
                chunk = os.read(descriptor, min(1 << 20, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            if len(payload) > max_bytes:
                raise DatasetIOError(f"{name}: exceeds the {max_bytes}-byte verification limit")
            self._assert_stable(name, before, os.fstat(descriptor))
            return payload
        finally:
            os.close(descriptor)

    def read_text(self, name: str, *, max_bytes: int) -> str:
        try:
            return self.read_bytes(name, max_bytes=max_bytes).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DatasetIOError(f"{name}: is not valid UTF-8") from exc

    def digest(self, name: str, *, max_bytes: int = MAX_DATA_FILE_BYTES) -> tuple[str, int]:
        descriptor = self._open_regular(name)
        digest = hashlib.sha256()
        size = 0
        try:
            before = os.fstat(descriptor)
            if before.st_size > max_bytes:
                raise DatasetIOError(
                    f"{name}: {before.st_size} bytes exceeds the "
                    f"{max_bytes}-byte verification limit"
                )
            while True:
                chunk = os.read(descriptor, 1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise DatasetIOError(f"{name}: exceeds the {max_bytes}-byte verification limit")
                digest.update(chunk)
            self._assert_stable(name, before, os.fstat(descriptor))
            return digest.hexdigest(), size
        finally:
            os.close(descriptor)

    def entries(self) -> tuple[DatasetEntry, ...]:
        try:
            # pathlib cannot list relative to the already-open directory descriptor.
            names = os.listdir(self._fd)  # noqa: PTH208
        except OSError as exc:
            raise DatasetIOError(f"cannot list dataset directory {self.path}: {exc}") from exc
        if len(names) > MAX_DATASET_ENTRIES:
            raise DatasetIOError(
                f"dataset contains {len(names)} entries; limit is {MAX_DATASET_ENTRIES}"
            )
        entries: list[DatasetEntry] = []
        for name in sorted(names, key=lambda item: item.encode("utf-8", errors="surrogateescape")):
            try:
                metadata = os.stat(name, dir_fd=self._fd, follow_symlinks=False)
            except OSError as exc:
                raise DatasetIOError(f"cannot inspect dataset entry {name!r}: {exc}") from exc
            if stat.S_ISREG(metadata.st_mode):
                kind = "file"
            elif stat.S_ISLNK(metadata.st_mode):
                kind = "symlink"
            elif stat.S_ISDIR(metadata.st_mode):
                kind = "directory"
            else:
                kind = "special file"
            entries.append(DatasetEntry(name=name, kind=kind))
        return tuple(entries)


def digest_path(path: Path, *, max_bytes: int = MAX_DATA_FILE_BYTES) -> tuple[str, int]:
    """Digest a flat regular file without following its parent or leaf symlinks."""
    path = Path(path)
    with DatasetReader(path.parent) as reader:
        return reader.digest(path.name, max_bytes=max_bytes)
