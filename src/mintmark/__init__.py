"""Mintmark: deterministic, fully synthetic, Turkish-first labeled datasets.

The public surface of this package is deliberately small: ``mint`` and
``verify``, plus the dataclasses they return. Module-internal names carry no
compatibility promise and may change in any release.

The composition root lives in ``mintmark.minting`` rather than in a module
named ``mint``. A submodule and a package attribute cannot share a name: the
import system binds ``package.<name>`` to the submodule the moment it is loaded,
which is exactly how ``from mintmark import mint`` once handed callers a module
instead of the function. Keeping the two names distinct is what makes the
public function reachable under every import order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mintmark.engine.version import VERSION as _VERSION

__version__ = _VERSION

__all__ = ["__version__", "mint", "verify"]


def __getattr__(name: str) -> Callable[..., Any]:
    """Expose mint and verify without importing the world at package import.

    A bare ``import mintmark`` should not pull in jsonschema, the pack loader,
    and every lexicon. The CLI and the library both reach the same functions.
    The resolved function is bound into this module's namespace, so the lookup
    happens once and later attribute access is a plain read.
    """
    if name in {"mint", "verify"}:
        from mintmark import api

        function: Callable[..., Any] = getattr(api, name)
        globals()[name] = function
        return function
    raise AttributeError(f"module 'mintmark' has no attribute {name!r}")
