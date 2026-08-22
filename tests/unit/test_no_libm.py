"""No transcendental call reaches the mint path.

Invariant 15. libm results differ across platforms and across libm versions on
one platform, so a single `math.log` in the mint path would make the byte-level
determinism claim false on a machine nobody tested. The offline table generator
under `tools/` may use `math` freely; nothing under `src/` may.

This is an AST scan rather than a grep because a grep for "math." also matches
prose, and a grep cannot tell `math.log` from `logging`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "mintmark"
TOOLS = Path(__file__).resolve().parents[2] / "tools"
SOURCES = sorted(SRC.rglob("*.py"))

# Functions whose results are permitted to vary across libm implementations and
# are therefore banned from the mint path. Integer operations that happen to
# live in `math`, such as `isqrt` and `gcd`, are exact and are not listed.
FORBIDDEN_MATH = frozenset(
    {
        "log",
        "log2",
        "log10",
        "log1p",
        "exp",
        "expm1",
        "pow",
        "sqrt",
        "sin",
        "cos",
        "tan",
        "asin",
        "acos",
        "atan",
        "atan2",
        "sinh",
        "cosh",
        "tanh",
        "erf",
        "erfc",
        "gamma",
        "lgamma",
        "hypot",
        "fsum",
        "prod",
    }
)

# Modules that would bring transcendental or vectorized arithmetic in sideways.
FORBIDDEN_MODULES = frozenset({"numpy", "pandas", "scipy", "statistics", "random", "cmath"})


def test_source_tree_is_not_empty() -> None:
    assert SOURCES, f"no source files found under {SRC}"


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_forbidden_module_is_imported(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    offenders = imported & FORBIDDEN_MODULES
    assert not offenders, (
        f"{path.name} imports {sorted(offenders)}. These carry platform-dependent "
        "or floating-point arithmetic and are barred from the mint path."
    )


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_transcendental_call(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in FORBIDDEN_MATH:
            if isinstance(func.value, ast.Name) and func.value.id == "math":
                offenders.append(f"math.{func.attr} at line {node.lineno}")
        elif isinstance(func, ast.Name) and func.id in FORBIDDEN_MATH:
            offenders.append(f"{func.id} at line {node.lineno}")
    assert not offenders, (
        f"{path.name} calls {offenders}. Transcendental results vary across libm "
        "implementations; move the computation into tools/gen_tables.py and commit "
        "its output instead."
    )


@pytest.mark.parametrize("path", SOURCES, ids=lambda p: p.name)
def test_no_float_literal_in_the_mint_path(path: Path) -> None:
    """Emitted data carries no floats, and neither does the arithmetic behind it."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders = [
        f"{node.value!r} at line {node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, float)
    ]
    assert not offenders, f"{path.name} contains float literals: {offenders}"


def test_the_offline_generator_is_allowed_to_use_math() -> None:
    """The rule is about where the arithmetic runs, not about avoiding it.

    If this ever fails, the transcendental work has left the offline generator,
    which means it went somewhere it must not be.
    """
    source = (TOOLS / "gen_tables.py").read_text(encoding="utf-8")
    assert "math.exp" in source
    assert "math.erf" in source


def test_the_scan_would_catch_a_planted_call(tmp_path: Path) -> None:
    """A scan that has never rejected anything is not known to reject anything."""
    planted = tmp_path / "planted.py"
    planted.write_text("import math\n\ndef f(x):\n    return math.log(x)\n", encoding="utf-8")

    tree = ast.parse(planted.read_text(encoding="utf-8"))
    found = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in FORBIDDEN_MATH
    ]
    assert found, "the detection logic no longer recognizes a transcendental call"
