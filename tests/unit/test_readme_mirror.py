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


def callout(path: Path) -> str:
    """The Important callout, unwrapped into one line and lowercased.

    A blockquote wraps at the line, so a phrase like "legal advice" can be split
    by a newline and a continuation marker. Searching the raw text for it would
    fail on wording that is present and correct.
    """
    text = path.read_text(encoding="utf-8")
    block = text[text.index("> [!IMPORTANT]") :].split("\n\n")[0]
    unwrapped = " ".join(line.lstrip("> ").strip() for line in block.splitlines())
    return " ".join(unwrapped.split()).lower()


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
    """Turkish runs about as long as English for the same content, never shorter."""
    english = len(ENGLISH.read_text(encoding="utf-8"))
    turkish = len(TURKISH.read_text(encoding="utf-8"))
    assert turkish > english * 0.9, (
        f"the Turkish mirror is {turkish} characters against {english}; that is a "
        "summary rather than a mirror"
    )


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_carries_the_required_blocks(path: Path) -> None:
    """Section 3.2 of the repository standard, in the family's header style.

    The title is an HTML heading rather than a markdown one, because the family's
    READMEs centre their header block. The requirement is that each block is
    present and in order, not that it is written in any particular syntax.
    """
    text = path.read_text(encoding="utf-8")
    assert '<h1 align="center">Mintmark</h1>' in text, "no title block"

    claim = text.index('<p align="center"><strong>')
    important = text.index("> [!IMPORTANT]")
    quickstart = text.index("mintmark mint --pack example")
    # rindex, not index: the licence badge sits in the header block, so the first
    # occurrence of the licence name is not the licence section.
    licence = text.rindex("Apache-2.0")

    assert claim < important < quickstart < licence, "the required blocks are out of order"
    assert "TRADEMARKS.md" in text


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_states_what_the_tool_is_not(path: Path) -> None:
    """The Important callout has to actually carry the disclaimers."""
    block = callout(path)

    assert "anonymization" in block or "anonimleştir" in block, (
        "the callout does not say this is not anonymization of real data"
    )
    assert "legal advice" in block or "hukuki tavsiye" in block
    assert "compliance guarantee" in block or "uyumluluk garantisi" in block
    assert "limits" in block or "sınırlar" in block


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_discloses_the_phone_coincidence_limit(path: Path) -> None:
    """The one limitation that cannot be engineered away, stated in the callout."""
    block = callout(path)
    assert "phone" in block or "telefon" in block
    assert "coincide" in block or "çakış" in block


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_states_the_determinism_claim_with_its_platforms(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for platform in ("Linux x86_64", "Linux arm64", "macOS arm64"):
        assert platform in text, f"{path.name} does not name {platform}"
    assert "Windows" in text, "the unclaimed platform is not stated"


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_points_at_the_package_that_exists(path: Path) -> None:
    """This used to assert nothing was published, which held until something was.

    Section 3.3 forbids claiming a publication that has not happened. It does not
    forbid describing one that has, and the failure worth guarding now is the
    opposite one: a README telling a reader to install a name that is not there.
    """
    text = path.read_text(encoding="utf-8")
    assert "https://pypi.org/project/mintmark/" in text, (
        f"{path.name} does not link the published package"
    )
    assert "uv tool install mintmark" in text, f"{path.name} does not show how to install it"
    assert "git+https://github.com/lokomotifai/mintmark" not in text, (
        f"{path.name} still installs from git, which was the workaround for not being on an index"
    )


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_the_quickstart_uses_a_pack_a_reader_will_actually_have(path: Path) -> None:
    """`packs/example` is a path that exists only in a checkout.

    Somebody who installed from an index and followed the README hit an error,
    which is what the packaged-pack resolver exists to prevent. The quickstart
    has to use the form that works for them.
    """
    text = path.read_text(encoding="utf-8")
    assert "--pack example" in text
    assert "--pack packs/example" not in text


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_carries_the_family_navigation(path: Path) -> None:
    """The sibling link is how a reader finds the other language."""
    text = path.read_text(encoding="utf-8")
    other = "README.tr.md" if path is ENGLISH else "README.md"
    assert other in text, f"{path.name} does not link to {other}"
    assert "lokomotifai/pactmark" in text, "no family footer"


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_the_diagrams_referenced_by_each_readme_exist(path: Path) -> None:
    """A README promising a picture that is not committed shows a broken image."""
    text = path.read_text(encoding="utf-8")
    for asset in (
        "assets/readme/mint-pipeline.png",
        "assets/readme/mint-pipeline.svg",
        "assets/readme/family-topology.png",
        "assets/readme/family-topology.svg",
        "assets/brand/mintmark-logo.svg",
    ):
        assert asset in text, f"{path.name} does not reference {asset}"
        assert (REPO_ROOT / asset).exists(), f"{asset} is referenced but not committed"


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_every_diagram_carries_alt_text_a_screen_reader_can_use(path: Path) -> None:
    """A diagram with no alt text is a diagram some readers simply do not get."""
    for match in re.finditer(r"!\[([^\]]*)\]\(assets/", path.read_text(encoding="utf-8")):
        assert len(match.group(1)) > 60, (
            f"{path.name} has a diagram whose alt text is too short to replace it"
        )


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


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_names_the_release_that_matches_this_version(path: Path) -> None:
    """The badge and the package have to agree.

    A README pointing at a tag nobody cut, or at an older one whose artifacts no
    longer match this tree, is the likelier failure now that releases exist.
    """
    import re
    import tomllib

    version = tomllib.loads(
        (Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    text = path.read_text(encoding="utf-8")
    named = set(re.findall(r"/releases/tag/v(\d+\.\d+\.\d+)", text))
    assert named == {version}, (
        f"{path.name} names releases {sorted(named)} while the package is {version}"
    )


@pytest.mark.parametrize("path", [ENGLISH, TURKISH], ids=["en", "tr"])
def test_each_readme_claims_the_number_of_tests_that_exist(path: Path, request) -> None:
    """A count in a badge is a claim, and claims here have to hold.

    Asserted against what this run collected rather than a literal, so adding a
    test fails the build until the badge follows. Skipped when a subset is
    selected, because then the number is not the suite's.
    """
    import re

    collected = request.session.testscollected
    if collected < 100:
        pytest.skip("a subset was selected; the collected count is not the suite's")
    text = path.read_text(encoding="utf-8")
    claimed = {int(m) for m in re.findall(r"badge/tests?-(\d+)-", text)}
    assert claimed == {collected}, (
        f"{path.name} claims {sorted(claimed) or 'no'} tests; the suite collects {collected}"
    )
