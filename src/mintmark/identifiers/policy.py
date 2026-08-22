"""Identifier policy: the safe default and the opt-in validator mode."""

from __future__ import annotations

from enum import StrEnum


class IdentifierPolicy(StrEnum):
    """How an identifier engine forms its check digits.

    `SAFE` is the default and the only policy a reference dataset ships with. It
    emits values that are format-plausible and provably checksum-invalid, so a
    generated identifier cannot collide with any real issued one.

    `VALIDATOR` emits checksum-valid values. It exists so that a consumer can
    test their own validation logic against something that passes, it is opt-in
    per mint, and every dataset minted under it carries a warning block in its
    manifest. Working as documented is not a vulnerability.
    """

    SAFE = "safe"
    VALIDATOR = "validator"


def parse_policy(value: str) -> IdentifierPolicy:
    """Parse a policy name, failing closed on anything unrecognized."""
    try:
        return IdentifierPolicy(value)
    except ValueError:
        allowed = ", ".join(p.value for p in IdentifierPolicy)
        raise ValueError(f"unknown identifier policy {value!r}; allowed: {allowed}") from None
