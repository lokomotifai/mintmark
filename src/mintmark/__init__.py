"""Mintmark: deterministic, fully synthetic, Turkish-first labeled datasets.

The public surface of this package is deliberately small: ``mint`` and
``verify``, plus the dataclasses they return. Module-internal names carry no
compatibility promise and may change in any release.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__", "mint", "verify"]


def __getattr__(name: str) -> object:
    """Expose mint and verify without importing the world at package import.

    A bare ``import mintmark`` should not pull in jsonschema, the pack loader,
    and every lexicon. The CLI and the library both reach the same functions.
    """
    if name == "mint":
        from mintmark.mint import mint

        return mint
    if name == "verify":
        from mintmark.api import verify

        return verify
    raise AttributeError(f"module 'mintmark' has no attribute {name!r}")
