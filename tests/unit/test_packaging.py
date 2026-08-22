"""What ships, and what must not.

A source-tree test run passes whether or not the package data is declared, so
the packaging manifest is checked against a real build. This is the test that
catches a data directory nobody remembered to include, and the one that catches
private material reaching an artifact.
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST = REPO_ROOT / "dist"


def built(pattern: str) -> Path:
    matches = sorted(DIST.glob(pattern))
    if not matches:
        pytest.skip(f"no {pattern} in dist/; run `uv build` first")
    return matches[-1]


@pytest.fixture(scope="module")
def wheel_names() -> list[str]:
    with zipfile.ZipFile(built("*.whl")) as archive:
        return archive.namelist()


@pytest.fixture(scope="module")
def sdist_names() -> list[str]:
    with tarfile.open(built("*.tar.gz")) as archive:
        return archive.getnames()


REQUIRED_IN_WHEEL = [
    "mintmark/_data/schemas/pack.schema.json",
    "mintmark/_data/schemas/manifest.schema.json",
    "mintmark/_data/assets/tables/balances.json",
    "mintmark/_data/assets/tables/CHECKSUMS",
    "mintmark/_data/assets/denylist/institutions-tr.txt",
    "mintmark/_data/packs/example/pack.yaml",
    "mintmark/lexicons/data/given_names_tr.yaml",
    "mintmark/py.typed",
]


@pytest.mark.parametrize("name", REQUIRED_IN_WHEEL)
def test_the_wheel_carries_the_data_the_quickstart_needs(wheel_names: list[str], name: str) -> None:
    assert name in wheel_names, f"{name} is missing from the wheel"


def test_the_wheel_excludes_everything_private_or_developmental(
    wheel_names: list[str],
) -> None:
    for name in wheel_names:
        assert not name.startswith("tools/"), f"tooling shipped: {name}"
        assert not name.startswith("tests/"), f"tests shipped: {name}"
        assert "PLAN.md" not in name, "the local-only plan reached an artifact"
        assert "corpus" not in name, f"corpus material reached an artifact: {name}"


def test_the_sdist_carries_the_tests_and_the_tooling(sdist_names: list[str]) -> None:
    """A source distribution should let someone re-run the checks."""
    joined = "\n".join(sdist_names)
    assert "tests/" in joined
    assert "tools/gen_tables.py" in joined
    assert "PLAN.md" not in joined, "the local-only plan reached the sdist"


def test_the_installed_console_script_reports_its_version() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "mintmark.cli", "--version"],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    from mintmark import __version__

    assert __version__ in result.stdout + result.stderr


def test_the_package_declares_exactly_two_runtime_dependencies() -> None:
    import tomllib

    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]
    assert len(project["dependencies"]) == 2
    assert project["readme"] == "README.md", "the readme key was never restored"


def test_the_sbom_lists_the_runtime_dependencies() -> None:
    import json

    path = DIST / "sbom.json"
    if not path.exists():
        pytest.skip("no sbom.json in dist/; generate it at release time")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["bomFormat"] == "CycloneDX"
    names = {component["name"].lower() for component in document["components"]}
    assert {"jsonschema", "pyyaml"} <= names
