"""Workflow files are configuration, and configuration that does not parse is a
silent outage.

A workflow whose YAML is malformed does not fail loudly on the platform. GitHub
records a run that never had jobs, reports it under the file path rather than the
workflow name, and the check that was supposed to protect the branch simply never
runs. That failure mode is invisible in a green-looking checks list, so it is
caught here instead.
"""

from __future__ import annotations

import re
import tomllib
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


def test_publication_stays_behind_a_recorded_authorization() -> None:
    """Publication is an authorization checkpoint, not a merge decision.

    This used to assert that the release workflow had no automatic trigger, which
    was the only control available while the workflow refused to run at all. The
    control now sits where it belongs: the publishing job runs inside a GitHub
    environment whose approval is recorded and whose deployment branch policy
    admits only tags. A trigger is a weak proxy for that and the proxy is no
    longer what is being relied on, so the test checks the thing itself.
    """
    document = load(WORKFLOW_DIR / "release.yml")
    publish = document["jobs"]["publish"]

    environment = publish.get("environment")
    assert environment, "the publishing job runs outside any environment gate"
    assert environment["name"] == "pypi", environment

    triggers = next(document[key] for key in ON_KEYS if key in document)
    assert set(triggers) <= {"push", "workflow_dispatch"}, triggers
    assert triggers.get("push", {}).get("tags") == ["v*"], (
        "publication may be reached from a version tag and from nothing else"
    )


def test_only_the_publishing_job_may_mint_an_identity_token() -> None:
    """`id-token: write` is what PyPI trusts. Nothing else needs it."""
    document = load(WORKFLOW_DIR / "release.yml")
    for name, job in document["jobs"].items():
        writes_token = job.get("permissions", {}).get("id-token") == "write"
        assert writes_token == (name == "publish"), (
            f"job {name!r} sets id-token: write and is not the publishing job"
        )


def test_the_release_workflow_refuses_a_tag_that_disagrees_with_the_package() -> None:
    """A version on PyPI cannot be replaced, so a mismatch has to fail closed.

    Deleting a release does not free its number either, which is why the workflow
    refuses rather than resolving the disagreement in either direction.
    """
    body = (WORKFLOW_DIR / "release.yml").read_text(encoding="utf-8")
    assert "GITHUB_REF_NAME" in body
    assert "mintmark.__version__" in body
    assert "exit 1" in body, "the version check no longer fails the run"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_every_external_action_is_pinned_to_an_immutable_commit(path: Path) -> None:
    document = load(path)
    for job_name, job in document["jobs"].items():
        for step in job["steps"]:
            uses = step.get("uses")
            if uses is None or uses.startswith("./"):
                continue
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", uses), (
                f"{path.name}:{job_name} uses mutable action reference {uses!r}"
            )


def test_uv_and_the_build_backend_are_exactly_locked() -> None:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)
    assert project["build-system"]["requires"] == ["hatchling==1.31.0"]
    assert "hatchling==1.31.0" in project["dependency-groups"]["dev"]
    assert project["tool"]["uv"]["required-version"] == "==0.12.3"
    lock = (REPO_ROOT / "uv.lock").read_text(encoding="utf-8")
    assert 'name = "hatchling"\nversion = "1.31.0"' in lock


def test_pull_request_code_never_receives_the_private_canary() -> None:
    document = load(WORKFLOW_DIR / "ci.yml")
    steps = document["jobs"]["canary"]["steps"]
    secret_steps = [step for step in steps if "MINTMARK_CANARY" in step.get("env", {})]
    assert len(secret_steps) == 1
    condition = secret_steps[0].get("if", "")
    assert "github.event_name == 'push'" in condition
    assert "refs/heads/main" in condition
    assert any(
        step.get("if") == "github.event_name == 'pull_request'"
        and "tests/unit/test_canary.py" in step.get("run", "")
        for step in steps
    )


def test_release_scans_and_seals_the_exact_built_artifacts_before_oidc() -> None:
    document = load(WORKFLOW_DIR / "release.yml")
    build_steps = document["jobs"]["build"]["steps"]
    publish_steps = document["jobs"]["publish"]["steps"]
    build_text = "\n".join(step.get("run", "") for step in build_steps)
    publish_text = "\n".join(step.get("run", "") for step in publish_steps)

    assert "uv build --no-build-isolation" in build_text
    assert "uv export --locked --no-dev --no-emit-project" in build_text
    assert "tools/canary.py dist/" in build_text
    assert "sha256sum mintmark-*.whl mintmark-*.tar.gz" in build_text
    assert "sha256sum -c SHA256SUMS" in publish_text
    publisher = publish_steps[-1]
    assert publisher["uses"].startswith("pypa/gh-action-pypi-publish@")
    assert publisher["with"]["verify-metadata"] is True
    canary = next(step for step in build_steps if "MINTMARK_CANARY" in step.get("env", {}))
    assert "refs/tags/v" in canary.get("if", "")
