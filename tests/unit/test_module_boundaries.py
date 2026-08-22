"""The engine imports only the standard library, proven by reading the source.

`import-linter` enforces the same rule from the import graph. This test reads
the abstract syntax tree instead, which catches two things the graph does not:
an import that is unreachable at runtime but present in the file, and a
dependency added to a module that no other module imports yet.

The stdlib-only rule is not a style preference. It is what makes the determinism
claim checkable: every value the engine produces comes from arithmetic this
repository specifies, not from a third party's release schedule.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "mintmark"
ENGINE = SRC / "engine"
ENGINE_MODULES = sorted(ENGINE.glob("*.py"))

STDLIB = frozenset(sys.stdlib_module_names)


def top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_engine_package_is_not_empty() -> None:
    assert ENGINE_MODULES, f"no engine modules found under {ENGINE}"


@pytest.mark.parametrize("path", ENGINE_MODULES, ids=lambda p: p.name)
def test_engine_module_imports_only_stdlib_or_its_own_package(path: Path) -> None:
    foreign = {
        name
        for name in top_level_imports(path)
        if name not in STDLIB and name != "mintmark" and not name.startswith("_")
    }
    assert not foreign, (
        f"{path.name} imports {sorted(foreign)}, which is neither the standard "
        "library nor mintmark itself. The engine's dependency surface is the "
        "determinism claim's surface."
    )


@pytest.mark.parametrize("path", ENGINE_MODULES, ids=lambda p: p.name)
def test_engine_module_does_not_reach_into_a_sibling_package(path: Path) -> None:
    """`engine` sits at the bottom of the layer stack and imports nothing above it."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    reached: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("mintmark."):
            second = node.module.split(".")[1]
            if second != "engine":
                reached.add(node.module)
    assert not reached, f"{path.name} imports {sorted(reached)} from outside engine"


@pytest.mark.parametrize("path", sorted(SRC.rglob("*.py")), ids=lambda p: str(p.name))
def test_no_dynamic_imports_anywhere_in_the_package(path: Path) -> None:
    """A dynamic import would make the dependency graph unverifiable statically.

    `import-linter` reads the graph; a call to `importlib.import_module` or to
    `__import__` hides an edge from it, so the contract would pass while the
    real dependency direction had already been broken.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "__import__":
            offenders.append("__import__")
        elif isinstance(func, ast.Attribute) and func.attr in {"import_module", "__import__"}:
            offenders.append(f"...{func.attr}")
    assert not offenders, f"{path.name} performs a dynamic import: {offenders}"
