"""The canary check is proven to fire, not only to pass.

Section 7.2 of the repository standard requires that a private-corpus canary be
absent from the tree and from built artifacts. A check that has never been
observed catching a planted string is not known to catch anything.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CANARY_TOOL = REPO_ROOT / "tools" / "canary.py"

# A canary used only by this test. It is not the repository's canary, and the
# tool is pointed at a matching digest through the environment so that these
# tests never need the real string.
TEST_CANARY = "canary-fixture-do-not-ship-9f2b"


def run_canary(
    *targets: Path, canary: str = TEST_CANARY, digest: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the tool with its expected digest patched to match `canary`.

    The tool refuses a canary that does not match its committed digest, which is
    the behavior `test_wrong_canary_is_refused` covers. Here the digest is
    overridden so that the scanning behavior itself can be tested.
    """
    source = CANARY_TOOL.read_text(encoding="utf-8")
    expected = digest if digest is not None else hashlib.sha256(canary.encode()).hexdigest()
    patched = source.replace(
        source.split("EXPECTED_DIGEST = ")[1].split("\n")[0],
        f'"{expected}"',
        1,
    )
    tool = Path(os.environ["CANARY_TMP"]) / "canary_under_test.py"
    tool.write_text(patched, encoding="utf-8")

    env = dict(os.environ, MINTMARK_CANARY=canary)
    return subprocess.run(
        [sys.executable, str(tool), *[str(t) for t in targets]],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_clean_tree_passes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CANARY_TMP", str(tmp_path))
    (tmp_path / "ordinary.txt").write_text("nothing to see here\n", encoding="utf-8")
    result = run_canary(tmp_path)
    assert result.returncode == 0, result.stderr


def test_planted_canary_is_found_and_the_file_is_named(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CANARY_TMP", str(tmp_path))
    leaked = tmp_path / "leaked.md"
    leaked.write_text(f"internal note mentioning {TEST_CANARY} inline\n", encoding="utf-8")
    result = run_canary(tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "leaked.md" in result.stderr


def test_canary_inside_a_built_wheel_is_found(tmp_path: Path, monkeypatch) -> None:
    """A tree can be clean while an artifact is not; the artifact is what ships."""
    monkeypatch.setenv("CANARY_TMP", str(tmp_path))
    wheel = tmp_path / "sample-0.1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("sample/__init__.py", "# clean\n")
        zf.writestr("sample/_data/notes.txt", f"leaked {TEST_CANARY}\n")
    result = run_canary(wheel)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "notes.txt" in result.stderr


def test_wrong_canary_is_refused_rather_than_passing_quietly(tmp_path: Path, monkeypatch) -> None:
    """Scanning for the wrong string is worse than not scanning at all."""
    monkeypatch.setenv("CANARY_TMP", str(tmp_path))
    (tmp_path / "ordinary.txt").write_text("nothing to see here\n", encoding="utf-8")
    result = run_canary(tmp_path, canary="not-the-right-canary", digest="0" * 64)
    assert result.returncode != 0
    assert "does not match the committed digest" in (result.stderr + result.stdout)


def test_missing_canary_is_refused(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("CANARY_TMP", str(tmp_path))
    env = dict(os.environ)
    env.pop("MINTMARK_CANARY", None)
    result = subprocess.run(
        [sys.executable, str(CANARY_TOOL), str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode != 0
    assert "no canary supplied" in (result.stderr + result.stdout)
