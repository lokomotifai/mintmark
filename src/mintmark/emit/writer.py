"""Atomic output: a mint directory is complete or absent, never half-written.

A mint can take minutes. Interrupting one must not leave a directory that looks
like a dataset, because the thing that makes it a dataset is the manifest, and a
partial directory with no manifest is indistinguishable from a finished one to
anything that only globs for JSONL files.

So a mint writes into a sibling staging directory and moves it into place after
the manifest and checksums are complete. The move is a single rename on the same
filesystem, which is atomic on every platform this project supports.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO


class StagedOutput:
    """A directory being built, not yet visible at its final path."""

    __slots__ = ("_committed", "_directory_fd", "_identity", "_staging", "_target")

    def __init__(self, target: Path) -> None:
        self._target = target
        target.parent.mkdir(parents=True, exist_ok=True)
        self._staging = Path(
            tempfile.mkdtemp(prefix=f".{target.name}.staging-", dir=target.parent)
        )
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        self._directory_fd = os.open(self._staging, flags)
        metadata = os.fstat(self._directory_fd)
        self._identity = (metadata.st_dev, metadata.st_ino)
        self._committed = False

    @property
    def path(self) -> Path:
        return self._staging

    def open(self, name: str) -> TextIO:
        """Open a file in the staging directory with canonical newline handling.

        newline="" stops Python from translating LF into CRLF on Windows. The
        determinism claim does not cover Windows, but a file whose line endings
        depend on where it was written would be a defect anywhere.
        """
        if not name or Path(name).name != name or name in {".", ".."}:
            raise ValueError(f"staged output names are single file names, got {name!r}")
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        descriptor = os.open(name, flags, 0o600, dir_fd=self._directory_fd)
        return os.fdopen(descriptor, "w", encoding="utf-8", newline="")

    def _assert_owned_staging_path(self) -> None:
        metadata = self._staging.lstat()
        if self._staging.is_symlink() or (metadata.st_dev, metadata.st_ino) != self._identity:
            raise RuntimeError("the staging directory path changed during minting")

    def commit(self) -> Path:
        self._assert_owned_staging_path()
        if self._target.exists() or self._target.is_symlink():
            raise FileExistsError(
                f"{self._target} already exists. A mint never overwrites an existing "
                "output directory: the old one may be a published dataset."
            )
        self._staging.rename(self._target)
        self._committed = True
        return self._target

    def discard(self) -> None:
        try:
            self._assert_owned_staging_path()
        except (FileNotFoundError, RuntimeError):
            return
        shutil.rmtree(self._staging, ignore_errors=True)

    def close(self) -> None:
        if self._directory_fd >= 0:
            os.close(self._directory_fd)
            self._directory_fd = -1


@contextmanager
def staged_output(target: Path) -> Iterator[StagedOutput]:
    """Build an output directory, publishing it only on success.

    Any exception, including a keyboard interrupt, removes the staging directory
    on the way out. What a consumer sees is either a complete mint or nothing.
    """
    target = Path(target)
    if target.exists() or target.is_symlink():
        raise FileExistsError(
            f"{target} already exists. A mint never overwrites an existing output directory: "
            "the old one may be a published dataset."
        )
    staged = StagedOutput(target)
    try:
        yield staged
        if not staged._committed:
            staged.commit()
    finally:
        if not staged._committed:
            staged.discard()
        staged.close()
