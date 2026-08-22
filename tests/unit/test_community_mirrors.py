"""Every English community document has a Turkish mirror that stays in step.

The audience for this project reads Turkish. A README mirror alone leaves a
contributor reading the contribution rules, the conduct rules, and the security
policy in a second language, which is the opposite of what the mirror was for.

These tests treat a mirror as a document, not a courtesy: it exists, it matches
the original's structure, it is not a summary, and each side points at the other.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# README is covered by its own suite, which checks claims these tests cannot.
MIRRORED = ("CODE_OF_CONDUCT", "CONTRIBUTING", "GOVERNANCE", "SECURITY", "SUPPORT")
HEADING = re.compile(r"^(#{1,6})\s", re.MULTILINE)


def levels(path: Path) -> list[int]:
    return [len(m.group(1)) for m in HEADING.finditer(path.read_text(encoding="utf-8"))]


@pytest.mark.parametrize("stem", MIRRORED)
def test_the_turkish_mirror_exists(stem: str) -> None:
    assert (ROOT / f"{stem}.md").exists(), f"{stem}.md is missing"
    assert (ROOT / f"{stem}.tr.md").exists(), (
        f"{stem}.tr.md is missing. An English-only community document asks a "
        f"Turkish reader to do the project's work in a second language."
    )


@pytest.mark.parametrize("stem", MIRRORED)
def test_the_heading_structures_match(stem: str) -> None:
    english = levels(ROOT / f"{stem}.md")
    turkish = levels(ROOT / f"{stem}.tr.md")
    assert english == turkish, (
        f"{stem}: the mirror has diverged in structure. {english} against {turkish}"
    )


@pytest.mark.parametrize("stem", MIRRORED)
def test_the_mirror_is_not_a_summary(stem: str) -> None:
    """A mirror that shrank is a mirror somebody stopped maintaining."""
    english = len((ROOT / f"{stem}.md").read_text(encoding="utf-8"))
    turkish = len((ROOT / f"{stem}.tr.md").read_text(encoding="utf-8"))
    assert turkish >= english * 0.75, (
        f"{stem}: the Turkish text is {turkish} characters against {english}. "
        f"That is a summary, not a mirror."
    )


@pytest.mark.parametrize("stem", MIRRORED)
def test_each_side_points_at_the_other(stem: str) -> None:
    english = (ROOT / f"{stem}.md").read_text(encoding="utf-8")
    turkish = (ROOT / f"{stem}.tr.md").read_text(encoding="utf-8")
    assert f'href="{stem}.tr.md"' in english, f"{stem}.md does not link its mirror"
    assert f'href="{stem}.md"' in turkish, f"{stem}.tr.md does not link the original"


def test_the_conduct_mirror_records_that_it_is_not_the_official_translation() -> None:
    """The Contributor Covenant publishes Turkish at 2.0; this repository adapts 2.1.

    Presenting our own rendering as the official translation would be a claim
    nobody checked, which is the failure mode this project's verification record
    exists to prevent.
    """
    text = (ROOT / "CODE_OF_CONDUCT.tr.md").read_text(encoding="utf-8")
    assert "resmî çeviri değildir" in text
    assert "contributor-covenant.org/tr/version/2/0" in text
