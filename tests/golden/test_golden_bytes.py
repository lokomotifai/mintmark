"""Invariant 1: identical inputs produce byte-identical outputs.

This is the claim the product rests on, so it is checked against committed bytes
rather than against a re-run of the same code. A test that mints twice in one
process proves the code is a function of its inputs; only committed bytes prove
that today's code is the same function yesterday's was.

If a test here fails, do not update the golden files to make it pass. Emitted
bytes moving for a fixed seed breaks the reproducibility of every published
manifest, and that is a major version event with a decision behind it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mintmark.cli import EXIT_OK, main
from mintmark.mint import mint

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK = REPO_ROOT / "packs" / "example"
GOLDEN = Path(__file__).resolve().parent / "demo-run"
DIGESTS = json.loads((GOLDEN / "DIGESTS.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def fresh(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("golden") / "run"
    mint(pack=PACK, recipe="demo", seed=42, out=out, invocation="pytest")
    return out


@pytest.mark.golden
@pytest.mark.parametrize("name", sorted(DIGESTS["digests"]))
def test_output_matches_the_committed_bytes(fresh: Path, name: str) -> None:
    actual = (fresh / name).read_bytes()
    expected = (GOLDEN / name).read_bytes()
    assert actual == expected, (
        f"{name} differs from the committed golden output. Emitted bytes moved for "
        "a fixed seed, which breaks every published manifest. This is a major "
        "version event, not a golden file to refresh."
    )


@pytest.mark.golden
@pytest.mark.parametrize("name", sorted(DIGESTS["digests"]))
def test_output_matches_the_recorded_digest(fresh: Path, name: str) -> None:
    actual = hashlib.sha256((fresh / name).read_bytes()).hexdigest()
    assert actual == DIGESTS["digests"][name]


@pytest.mark.golden
def test_minting_twice_in_one_process_is_identical(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    mint(pack=PACK, recipe="demo", seed=42, out=first, invocation="pytest")
    mint(pack=PACK, recipe="demo", seed=42, out=second, invocation="pytest")
    for name in sorted(DIGESTS["digests"]):
        assert (first / name).read_bytes() == (second / name).read_bytes()


@pytest.mark.golden
def test_a_different_seed_produces_different_bytes(tmp_path: Path) -> None:
    """The seed has to matter, or the determinism claim is trivially true."""
    other = tmp_path / "other"
    mint(pack=PACK, recipe="demo", seed=43, out=other, invocation="pytest")
    assert (other / "customer.jsonl").read_bytes() != (GOLDEN / "customer.jsonl").read_bytes()


@pytest.mark.golden
def test_a_different_policy_produces_different_bytes(tmp_path: Path) -> None:
    out = tmp_path / "validator"
    mint(
        pack=PACK,
        recipe="demo",
        seed=42,
        out=out,
        identifier_policy="validator",
        invocation="pytest",
    )
    assert (out / "customer.jsonl").read_bytes() != (GOLDEN / "customer.jsonl").read_bytes()


@pytest.mark.golden
def test_reproduce_agrees_with_the_committed_run(tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "run"
    mint(pack=PACK, recipe="demo", seed=42, out=out, invocation="pytest")
    monkeypatch.chdir(REPO_ROOT)
    assert main(["reproduce", str(out)]) == EXIT_OK


@pytest.mark.golden
def test_the_golden_files_are_small_enough_to_read(fresh: Path) -> None:
    """A golden file nobody can diff is a golden file nobody checks."""
    for name in sorted(DIGESTS["digests"]):
        lines = (GOLDEN / name).read_text(encoding="utf-8").splitlines()
        assert len(lines) <= 200, f"{name} has grown past what a reviewer will read"


@pytest.mark.golden
def test_the_golden_run_carries_its_provenance_note() -> None:
    """So that a future contributor knows what these bytes are and why."""
    assert DIGESTS["seed"] == "42"
    assert DIGESTS["identifier_policy"] == "safe"
    assert "major version event" in DIGESTS["_note"]
