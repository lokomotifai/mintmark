"""The prose lint is proven to fail, not only to pass.

A lint that has never been observed rejecting bad input is not known to work.
These tests are the executable form of that rule: each one plants a violation
the repository standard forbids and asserts that `tools/mdlint.py` names it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MDLINT = REPO_ROOT / "tools" / "mdlint.py"

CLEAN = "# A sentence case heading\n\nOrdinary prose with a hyphen-minus - like this.\n"


def run_mdlint(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MDLINT), str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def write(tmp_path: Path, body: str, name: str = "sample.md") -> Path:
    (tmp_path / name).write_text(body, encoding="utf-8")
    return tmp_path


def test_clean_prose_passes(tmp_path: Path) -> None:
    result = run_mdlint(write(tmp_path, CLEAN))
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("body", "rule"),
    [
        ("# Heading\n\nAn em dash — appears here.\n", "forbidden-dash"),
        # The dash literals are the fixture. RUF001 flags them as ambiguous,
        # which is precisely the property that makes them worth banning.
        ("# Heading\n\nAn en dash – appears here.\n", "forbidden-dash"),  # noqa: RUF001
        ("# Heading\n\nA seamless experience.\n", "banned-vocabulary"),
        ("# Heading\n\nThis is a powerful tool.\n", "banned-vocabulary"),
        ("# Heading\n\nBir devrim niteliginde.\n", "banned-vocabulary"),
        ("# Heading\n\nYeni nesil bir arac.\n", "banned-vocabulary"),
        ("# Heading\n\nKusursuz bir sonuc.\n", "banned-vocabulary"),
        ("# This Is A Title Cased Heading\n\nProse.\n", "sentence-case-heading"),
    ],
)
def test_violations_are_rejected_and_named(tmp_path: Path, body: str, rule: str) -> None:
    result = run_mdlint(write(tmp_path, body))
    assert result.returncode == 1, f"expected rejection, got {result.returncode}"
    assert rule in result.stderr, result.stderr
    assert "sample.md" in result.stderr, result.stderr


def test_fenced_code_is_exempt(tmp_path: Path) -> None:
    """Commands and identifiers are not prose and must not trip the rules."""
    body = "# Heading\n\n```\nrun --seamless --flag — value\n```\n"
    result = run_mdlint(write(tmp_path, body))
    assert result.returncode == 0, result.stderr


def test_inline_code_is_exempt(tmp_path: Path) -> None:
    body = "# Heading\n\nThe flag `--powerful` is spelled exactly so.\n"
    result = run_mdlint(write(tmp_path, body))
    assert result.returncode == 0, result.stderr


def test_allowlist_with_a_reason_exempts_one_line(tmp_path: Path) -> None:
    body = (
        "# Heading\n\n"
        "<!-- mdlint-allow: quoting an upstream release note verbatim -->\n"
        "They called it a seamless upgrade.\n"
    )
    result = run_mdlint(write(tmp_path, body))
    assert result.returncode == 0, result.stderr


def test_allowlist_block_exempts_a_range(tmp_path: Path) -> None:
    body = (
        "# Heading\n\n"
        "<!-- mdlint-allow-start: quoting a third-party model card -->\n"
        "A seamless experience.\n"
        "A powerful result.\n"
        "<!-- mdlint-allow-end -->\n"
        "Ordinary prose resumes.\n"
    )
    result = run_mdlint(write(tmp_path, body))
    assert result.returncode == 0, result.stderr


def test_allowlist_stops_at_the_end_marker(tmp_path: Path) -> None:
    """An exemption that leaked past its block would silently disable the lint."""
    body = (
        "# Heading\n\n"
        "<!-- mdlint-allow-start: quoting a third-party model card -->\n"
        "A seamless experience.\n"
        "<!-- mdlint-allow-end -->\n"
        "This powerful claim is ours and must be caught.\n"
    )
    result = run_mdlint(write(tmp_path, body))
    assert result.returncode == 1, result.stderr
    assert "banned-vocabulary" in result.stderr


def test_allowlist_without_a_reason_is_itself_an_error(tmp_path: Path) -> None:
    body = "# Heading\n\n<!-- mdlint-allow: -->\nA seamless experience.\n"
    result = run_mdlint(write(tmp_path, body))
    assert result.returncode == 1, result.stderr
    assert "allowlist-without-reason" in result.stderr


def test_unclosed_allowlist_block_is_reported(tmp_path: Path) -> None:
    body = "# Heading\n\n<!-- mdlint-allow-start: quoting something -->\nA seamless experience.\n"
    result = run_mdlint(write(tmp_path, body))
    assert result.returncode == 1, result.stderr
    assert "allowlist-unclosed" in result.stderr


def test_repository_prose_is_clean() -> None:
    """The rule applies to this repository, not only to fixtures."""
    result = run_mdlint(REPO_ROOT)
    assert result.returncode == 0, result.stderr
