#!/usr/bin/env python3
"""Private-corpus canary check.

Section 7.2 of the lokomotifai public repository standard requires that a known
canary string from the organization's private materials be absent from the
repository tree and from built artifacts. This script is that check.

The canary itself is never committed. Committing it would plant the very string
the check exists to find, and the first run would fail on its own tripwire.
Instead the canary is supplied at run time and this repository commits only its
SHA-256, so that a run can prove it was given the right string rather than an
empty one:

    MINTMARK_CANARY='...' python tools/canary.py .
    python tools/canary.py . --canary-file ~/private/canary.txt

The committed digest is a tripwire, not a secret. A short canary phrase is
recoverable from its hash by anyone who guesses it, which costs nothing here:
the check detects accidental leakage of private planning material, and it does
not defend against an adversary who already holds the material.

Scanning covers text files in the tree and, when a path is given, the contents
of built sdists and wheels. Binary files are compared byte-wise against the
UTF-8 encoding of the canary.

Exit codes: 0 clean, 1 canary found, 2 usage or configuration error.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Iterator
from pathlib import Path

# SHA-256 of the canary phrase for this repository family. Set by WP-00 and
# changed only when the canary itself is rotated, which is a Decision Log event.
EXPECTED_DIGEST = "b0c48e6c4b8ccb15439bebcec60a9939806771157a38407686782c85ede7cd16"

SKIP_DIRS = frozenset(
    {".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}
)
ARCHIVE_SUFFIXES = frozenset({".whl", ".zip", ".tar", ".gz", ".tgz"})


def load_canary() -> str:
    value = os.environ.get("MINTMARK_CANARY", "").strip()
    if value:
        return value
    raise SystemExit(
        "canary: no canary supplied. Set MINTMARK_CANARY or pass --canary-file.\n"
        "The canary is never committed to this repository; see the module docstring."
    )


def verify_digest(canary: str) -> None:
    digest = hashlib.sha256(canary.encode("utf-8")).hexdigest()
    if digest != EXPECTED_DIGEST:
        raise SystemExit(
            "canary: the supplied canary does not match the committed digest.\n"
            f"  expected {EXPECTED_DIGEST}\n  received {digest}\n"
            "A mismatch means the check would scan for the wrong string, which is "
            "worse than not running it at all."
        )


def tracked_files(root: Path) -> Iterator[Path]:
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for rel in out.split("\0"):
            if rel:
                yield root / rel
        return
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    for path in root.rglob("*"):
        if path.is_file() and not any(part in SKIP_DIRS for part in path.parts):
            yield path


def scan_archive(path: Path, needle: bytes) -> list[str]:
    hits: list[str] = []
    try:
        if path.suffix in {".whl", ".zip"}:
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    if needle in zf.read(name):
                        hits.append(f"{path}::{name}")
        elif path.name.endswith((".tar.gz", ".tgz", ".tar")):
            with tarfile.open(path) as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    handle = tf.extractfile(member)
                    if handle is not None and needle in handle.read():
                        hits.append(f"{path}::{member.name}")
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
        raise SystemExit(f"canary: cannot read archive {path}: {exc}") from exc
    return hits


def scan(root: Path, canary: str) -> list[str]:
    needle = canary.encode("utf-8")
    hits: list[str] = []

    if root.is_file():
        targets: Iterator[Path] = iter([root])
    else:
        targets = tracked_files(root)

    for path in targets:
        if not path.is_file():
            continue
        if path.suffix in ARCHIVE_SUFFIXES or path.name.endswith(".tar.gz"):
            hits.extend(scan_archive(path, needle))
            continue
        try:
            if needle in path.read_bytes():
                hits.append(str(path))
        except OSError:
            continue
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "targets", nargs="*", default=["."], help="directories, files, or built artifacts to scan"
    )
    parser.add_argument(
        "--canary-file", type=Path, help="read the canary from this file instead of the environment"
    )
    parser.add_argument(
        "--print-digest",
        action="store_true",
        help="print the SHA-256 of the supplied canary and exit",
    )
    args = parser.parse_args(argv)

    if args.canary_file:
        try:
            canary = args.canary_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            print(f"canary: cannot read {args.canary_file}: {exc}", file=sys.stderr)
            return 2
    else:
        canary = load_canary()

    if args.print_digest:
        print(hashlib.sha256(canary.encode("utf-8")).hexdigest())
        return 0

    verify_digest(canary)

    all_hits: list[str] = []
    for target in args.targets or ["."]:
        path = Path(target).resolve()
        if not path.exists():
            print(f"canary: no such path: {path}", file=sys.stderr)
            return 2
        all_hits.extend(scan(path, canary))

    if all_hits:
        print("canary: private-corpus canary found in:", file=sys.stderr)
        for hit in all_hits:
            print(f"  {hit}", file=sys.stderr)
        print(
            "\nPrivate planning material has leaked into the tree or an artifact.", file=sys.stderr
        )
        return 1

    print(f"canary: clean, {len(args.targets or ['.'])} target(s) scanned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
