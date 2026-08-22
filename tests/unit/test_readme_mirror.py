"""Invariant 18: the Turkish mirror is a mirror, not a summary.

The repository standard requires README.tr.md to be a full mirror updated in the
same change as README.md. A mirror that drifts is worse than an absent one: a
Turkish reader trusts it and gets last quarter's claims.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGLISH = REPO_ROOT / "README.md"
TURKISH = REPO_ROOT / "README.tr.md"

HEADING = re.compile(r"^(#{1,6})\s", re.MULTILINE)
FENCE = re.compile(r"^(?: {4}.*\n?)+", re.MULTILINE)


def heading_levels(path: Path) -> list[int]:
    return [len(m.group(1)) for m in HEADING.finditer(path.read_text(encoding="utf-8"))]


def test_both_readmes_exist() -> None:
    assert ENGLISH.exists()
    assert TURKISH.exists(), "the Turkish mirror is required, not optional"


def test_the_heading_structures_match() -> None:
    """Same shape, section for section, at the same nesting depth."""
    assert heading_levels(ENGLISH) == heading_levels(TURKISH), (
        "the two READMEs have diverged in structure; a mirror that drifts gives a "
        "Turkish reader stale claims while looking current"
    )


def test_the_mirror_is_not_a_summary() -> None:
    """Turkish runs longer than English for the same content, never shorter."""
    english = len(ENGLISH.read_text(encoding="utf-8"))
    turkish = len(TURKISH.read_text(encoding="utf-8"))
    assert turkish > english * 0.85, (
        f"the Turkish mirror is {turkish} characters against {english}; that is a "
        "summary rather than a mirror"
    )


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_carries_the_required_blocks(path: Path) -> None:
    """Section 3.2 of the repository standard, in order."""
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Mintmark")
    assert "**" in text.split("\n")[2], "no one-line bold claim under the title"
    assert "> **" in text, "no Important callout"
    assert "mintmark mint --pack packs/example" in text, "no offline quickstart"
    assert "Apache-2.0" in text
    assert "TRADEMARKS.md" in text


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_states_what_the_tool_is_not(path: Path) -> None:
    text = path.read_text(encoding="utf-8").lower()
    for claim in ("anonymization", "anonimleştirilmesi"):
        if claim in text:
            break
    else:
        raise AssertionError("neither README says it is not anonymization of real data")
    assert "kvkk" in text or "compliance" in text or "uyumluluk" in text


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_discloses_the_phone_coincidence_limit(path: Path) -> None:
    """The one limitation that cannot be engineered away has to be stated."""
    text = path.read_text(encoding="utf-8").lower()
    assert "phone" in text or "telefon" in text
    assert "coincide" in text or "çakış" in text


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_states_the_determinism_claim_with_its_platforms(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for platform in ("Linux x86_64", "Linux arm64", "macOS arm64"):
        assert platform in text, f"{path.name} does not name {platform}"
    assert "Windows" in text, "the unclaimed platform is not stated"


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_neither_readme_claims_a_published_package(path: Path) -> None:
    """Nothing is published yet, and section 3.3 forbids claiming otherwise."""
    text = path.read_text(encoding="utf-8").lower()
    assert "pypi.org/project" not in text
    assert "available on pypi" not in text


def test_the_quickstart_output_block_matches_what_verify_prints(tmp_path: Path) -> None:
    """A README that promises output nobody re-ran is a README that goes stale."""
    from mintmark.cli import main

    out = tmp_path / "demo-run"
    main(
        [
            "mint",
            "--pack",
            str(REPO_ROOT / "packs" / "example"),
            "--recipe",
            "demo",
            "--seed",
            "42",
            "--out",
            str(out),
        ]
    )
    from mintmark.api import verify

    report = verify(out)
    rendered = report.render()

    english = ENGLISH.read_text(encoding="utf-8")
    for line in rendered.splitlines():
        assert line in english, f"README promises output that verify does not print: {line!r}"
