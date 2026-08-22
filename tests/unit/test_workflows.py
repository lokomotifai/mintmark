"""Workflow files are configuration, and configuration that does not parse is a
silent outage.

A workflow whose YAML is malformed does not fail loudly on the platform. GitHub
records a run that never had jobs, reports it under the file path rather than the
workflow name, and the check that was supposed to protect the branch simply never
runs. That failure mode is invisible in a green-looking checks list, so it is
caught here instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
WORKFLOWS = sorted(WORKFLOW_DIR.glob("*.yml"))

# PyYAML resolves an unquoted `on:` key to the boolean True, which is the YAML
# 1.1 behavior GitHub's own parser does not share. Both spellings are accepted
# here so the test checks structure rather than the quirk.
ON_KEYS: tuple[Any, ...] = ("on", True)


def load(path: Path) -> dict[Any, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_workflow_directory_is_not_empty() -> None:
    assert WORKFLOWS, f"no workflow files found under {WORKFLOW_DIR}"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_parses_and_has_the_required_shape(path: Path) -> None:
    document = load(path)
    assert isinstance(document, dict), f"{path.name} is not a mapping at its root"
    assert document.get("name"), f"{path.name} declares no name"
    assert any(key in document for key in ON_KEYS), f"{path.name} declares no trigger"

    jobs = document.get("jobs")
    assert isinstance(jobs, dict), f"{path.name} has no jobs mapping"
    assert jobs, f"{path.name} declares no jobs"

    for job_name, job in jobs.items():
        steps = job.get("steps")
        assert isinstance(steps, list), f"{path.name}:{job_name} has no step list"
        assert steps, f"{path.name}:{job_name} has no steps"
        for index, step in enumerate(steps):
            assert "run" in step or "uses" in step, (
                f"{path.name}:{job_name} step {index} neither runs nor uses anything"
            )


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_token_permissions_default_to_read_only(path: Path) -> None:
    """Section 6.3 of the repository standard, asserted rather than trusted."""
    document = load(path)
    permissions = document.get("permissions")
    assert permissions is not None, f"{path.name} does not pin token permissions"
    assert permissions.get("contents") == "read", (
        f"{path.name} grants contents: {permissions.get('contents')!r}, expected read"
    )


def test_required_ci_covers_the_three_supported_platforms() -> None:
    """The determinism claim names three platforms; CI must actually run on them."""
    document = load(WORKFLOW_DIR / "ci.yml")
    matrix = document["jobs"]["tests"]["strategy"]["matrix"]["os"]
    assert set(matrix) == {"ubuntu-latest", "ubuntu-24.04-arm", "macos-latest"}, (
        f"the test matrix is {matrix}; widening or narrowing it changes the claim"
    )


def test_release_workflow_stays_disabled() -> None:
    """Publication is an external authorization checkpoint, not a merge decision."""
    document = load(WORKFLOW_DIR / "release.yml")
    triggers = next(document[key] for key in ON_KEYS if key in document)
    assert set(triggers) == {"workflow_dispatch"}, (
        "the release workflow gained an automatic trigger; publication must stay "
        "behind a recorded authorization"
    )
    body = (WORKFLOW_DIR / "release.yml").read_text(encoding="utf-8")
    assert "exit 1" in body, "the disabled release workflow no longer refuses to run"
