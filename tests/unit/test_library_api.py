"""The library surface: `from mintmark import mint, verify` under every import order.

The package once exposed a submodule and a function under the same name,
`mint`. The import system binds `mintmark.mint` to the submodule the moment it
is loaded, so the documented function was reachable only until anything, the
CLI included, imported the composition root. No test used the public path, so
915 tests passed while the public path did not work.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK = REPO_ROOT / "packs" / "example"
SMALL = {"customer": 5, "transaction": 5}


def test_the_public_functions_are_functions(tmp_path: Path) -> None:
    from mintmark import mint, verify

    assert callable(mint)
    assert callable(verify)
    summary = mint(pack=PACK, recipe="demo", seed=1, out=tmp_path / "run", records=SMALL)
    assert summary.record_counts == SMALL
    report = verify(tmp_path / "run")
    assert report.ok, report.problems


def test_repeated_attribute_access_returns_the_same_function(tmp_path: Path) -> None:
    """The first lookup used to return the function and the second the module."""
    import mintmark

    first = mintmark.mint
    second = mintmark.mint
    assert first is second
    assert first is mintmark.api.mint
    first(pack=PACK, recipe="demo", seed=1, out=tmp_path / "a", records=SMALL)
    second(pack=PACK, recipe="demo", seed=1, out=tmp_path / "b", records=SMALL)


def test_the_function_survives_the_cli_being_imported_first(tmp_path: Path) -> None:
    """Import order must not decide what a name means."""
    code = (
        "import mintmark.cli\n"
        "from mintmark import mint, verify\n"
        "import types\n"
        "assert not isinstance(mint, types.ModuleType), type(mint)\n"
        f"summary = mint(pack={str(PACK)!r}, recipe='demo', seed=1, out={str(tmp_path / 'r')!r},"
        " records={'customer': 5, 'transaction': 5})\n"
        f"assert verify({str(tmp_path / 'r')!r}).ok\n"
        "print(summary.pack)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "mintmark-example"


def test_no_submodule_shares_the_public_function_name() -> None:
    """A submodule named `mint` would shadow the function again on first import."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("mintmark.mint")


def test_a_bare_import_stays_lazy() -> None:
    """`import mintmark` must not pull in the dependencies the CLI needs."""
    code = (
        "import sys, mintmark\n"
        "heavy = {'jsonschema', 'yaml', 'mintmark.minting', 'mintmark.manifest'}\n"
        "heavy &= set(sys.modules)\n"
        "print(sorted(heavy))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=False, cwd=REPO_ROOT
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]", result.stdout


def test_the_library_resolves_the_packaged_example_by_name(tmp_path: Path) -> None:
    """`pack="example"` reaches the shipped pack, exactly as `--pack example` does."""
    from mintmark import mint

    summary = mint(pack="example", recipe="demo", seed=1, out=tmp_path / "run", records=SMALL)
    assert summary.pack == "mintmark-example"


def test_unknown_attributes_still_raise() -> None:
    import mintmark

    with pytest.raises(AttributeError):
        _ = mintmark.no_such_thing
