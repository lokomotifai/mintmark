"""The engineering baseline WP-00 establishes, asserted rather than assumed."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import mintmark

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runtime_is_cpython_312() -> None:
    """The determinism claim covers CPython 3.12 only.

    A test run on another minor version proves nothing about the claim, so the
    suite refuses to run quietly on one.
    """
    assert sys.version_info[:2] == (3, 12), (
        f"expected CPython 3.12, running {sys.version.split()[0]}"
    )


def test_package_imports_and_reports_a_version() -> None:
    assert mintmark.__version__
    assert mintmark.__version__ == _project_version()


def test_runtime_dependency_surface_stays_two_entries() -> None:
    """PLAN.md section 10.4 fixes the runtime dependency list at two entries.

    Any addition is a recorded decision. This test is the mechanism that forces
    the decision to be made deliberately rather than in passing.
    """
    deps = _pyproject()["project"]["dependencies"]
    names = sorted(dep.split(">")[0].split("=")[0].split("<")[0].strip().lower() for dep in deps)
    assert names == ["jsonschema", "pyyaml"], (
        "the runtime dependency surface changed; record a decision before widening it"
    )


def test_requires_python_is_pinned_to_a_single_minor_version() -> None:
    spec = _pyproject()["project"]["requires-python"]
    assert spec == ">=3.12,<3.13", f"unexpected requires-python: {spec}"


def _pyproject() -> dict[str, object]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _project_version() -> str:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    version = project["version"]
    assert isinstance(version, str)
    return version
