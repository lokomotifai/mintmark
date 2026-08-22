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

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO


class StagedOutput:
    """A directory being built, not yet visible at its final path."""

    __slots__ = ("_committed", "_staging", "_target")

    def __init__(self, target: Path) -> None:
        self._target = target
        self._staging = target.parent / f".{target.name}.staging"
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
        path = self._staging / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.open("w", encoding="utf-8", newline="")

    def commit(self) -> Path:
        if self._target.exists():
            raise FileExistsError(
                f"{self._target} already exists. A mint never overwrites an existing "
                "output directory: the old one may be a published dataset."
            )
        self._staging.rename(self._target)
        self._committed = True
        return self._target

    def discard(self) -> None:
        if self._staging.exists():
            shutil.rmtree(self._staging, ignore_errors=True)


@contextmanager
def staged_output(target: Path) -> Iterator[StagedOutput]:
    """Build an output directory, publishing it only on success.

    Any exception, including a keyboard interrupt, removes the staging directory
    on the way out. What a consumer sees is either a complete mint or nothing.
    """
    target = Path(target)
    staged = StagedOutput(target)
    staged.discard()
    staged.path.mkdir(parents=True, exist_ok=False)
    try:
        yield staged
    except BaseException:
        staged.discard()
        raise
    else:
        if not staged._committed:
            staged.commit()
