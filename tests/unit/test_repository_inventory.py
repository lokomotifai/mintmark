"""The community files this repository is expected to carry, and their mirrors.

Not a style preference. Each of these answers a question a newcomer, a reporter,
or a legal reviewer actually asks, and an absent one sends them to open an issue
or to guess. The list is asserted so a repository cannot quietly drift below it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]

REQUIRED = [
    "README.md",
    "README.tr.md",
    "LICENSE",
    "LICENSE-DATASETS.md",
    "NOTICE",
    "CHANGELOG.md",
    "CITATION.cff",
    "CODE_OF_CONDUCT.md",
    "CODE_OF_CONDUCT.tr.md",
    "CONTRIBUTING.md",
    "CONTRIBUTING.tr.md",
    "GOVERNANCE.md",
    "GOVERNANCE.tr.md",
    "MAINTAINERS.md",
    "SECURITY.md",
    "SECURITY.tr.md",
    "SUPPORT.md",
    "SUPPORT.tr.md",
    "TRADEMARKS.md",
    "ORIGIN_AND_ATTRIBUTION.md",
    "THIRD_PARTY_NOTICES.md",
    "docs/kvkk.md",
    "docs/kvkk.tr.md",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/config.yml",
    ".github/ISSUE_TEMPLATE/bug.yml",
    ".github/ISSUE_TEMPLATE/proposal.yml",
    ".github/ISSUE_TEMPLATE/documentation.yml",
    ".github/ISSUE_TEMPLATE/question.yml",
    ".github/ISSUE_TEMPLATE/real-name.yml",
]


@pytest.mark.parametrize("relative", REQUIRED)
def test_the_file_exists_and_is_not_a_stub(relative: str) -> None:
    path = ROOT / relative
    assert path.exists(), f"{relative} is missing"
    assert path.stat().st_size > 120, f"{relative} is a stub"


@pytest.mark.parametrize(
    "relative",
    [r for r in REQUIRED if r.endswith(".yml") and "ISSUE_TEMPLATE" in r],
)
def test_every_issue_form_parses_and_declares_a_name(relative: str) -> None:
    """A malformed issue form does not fail loudly, it just stops appearing."""
    document = yaml.safe_load((ROOT / relative).read_text(encoding="utf-8"))
    if relative.endswith("config.yml"):
        assert document["blank_issues_enabled"] is False
        assert document["contact_links"]
        return
    assert document["name"], relative
    assert document["description"], relative
    assert document["body"], relative


def test_the_issue_forms_route_security_reports_away_from_public_issues() -> None:
    document = yaml.safe_load(
        (ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")
    )
    urls = " ".join(link["url"] for link in document["contact_links"])
    assert "security/advisories/new" in urls


def test_the_issue_forms_tell_a_turkish_reader_they_may_write_in_turkish() -> None:
    """The audience reads Turkish. An English-only form is a filter nobody chose."""
    document = yaml.safe_load(
        (ROOT / ".github/ISSUE_TEMPLATE/config.yml").read_text(encoding="utf-8")
    )
    assert any("Türkçe" in link["name"] for link in document["contact_links"])


def test_the_citation_file_names_this_repository() -> None:
    document = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    assert document["cff-version"] == "1.2.0"
    assert document["repository-code"].endswith(ROOT.name)
    assert document["authors"]


def test_the_dataset_license_file_states_the_terms_and_how_to_attribute() -> None:
    text = (ROOT / "LICENSE-DATASETS.md").read_text(encoding="utf-8")
    assert "CC-BY-4.0" in text
    assert "creativecommons.org/licenses/by/4.0/legalcode" in text
    assert "license.attribution" in text, "the file must say where the credit line lives"
    assert "CC0" in text, "the file must record what changed and why"
