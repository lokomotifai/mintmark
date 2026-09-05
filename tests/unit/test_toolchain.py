"""The engineering baseline WP-00 establishes, asserted rather than assumed."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import mintmark

REPO_ROOT = Path(__file__).resolve().parents[2]


SUPPORTED_MINORS = ((3, 12), (3, 13), (3, 14))


def test_runtime_is_a_supported_cpython() -> None:
    """The suite runs only on an interpreter the project supports.

    Every supported minor runs the same suite, golden bytes included, in
    required CI. A run on any other version proves nothing about the claim, so
    the suite refuses to run quietly on one.
    """
    assert sys.implementation.name == "cpython", sys.implementation.name
    assert sys.version_info[:2] in SUPPORTED_MINORS, (
        f"expected CPython {' or '.join(f'{a}.{b}' for a, b in SUPPORTED_MINORS)}, "
        f"running {sys.version.split()[0]}"
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


def test_requires_python_matches_the_supported_minors() -> None:
    """The metadata admits exactly the interpreters CI exercises, no more."""
    spec = _pyproject()["project"]["requires-python"]
    low, high = SUPPORTED_MINORS[0], SUPPORTED_MINORS[-1]
    assert spec == f">={low[0]}.{low[1]},<{high[0]}.{high[1] + 1}", spec
    classifiers = _pyproject()["project"]["classifiers"]
    assert isinstance(classifiers, list)
    assert [c for c in classifiers if "Python :: 3." in c] == [
        f"Programming Language :: Python :: {a}.{b}" for a, b in SUPPORTED_MINORS
    ]


def _pyproject() -> dict[str, object]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _project_version() -> str:
    project = _pyproject()["project"]
    assert isinstance(project, dict)
    version = project["version"]
    assert isinstance(version, str)
    return version
