"""Identifier engines: six systems, two policies, one shared contract.

Every engine exposes `generate(stream, policy)` and `is_checksum_valid(value)`.
The second is not a convenience. It is the same function `mintmark verify` runs
over every emitted file, which is what stops an engine from certifying its own
safety: a safe-mode claim is proven by surviving the check a consumer applies,
not by asserting that the corruption step ran.

`import-linter` holds this package to importing only `engine`.
"""

from __future__ import annotations

from types import ModuleType

from mintmark.identifiers import email, iban, pan, phone, tckn, vkn
from mintmark.identifiers.fold import fold, fold_for_local_part
from mintmark.identifiers.policy import IdentifierPolicy, parse_policy

# Engines whose output carries a checksum, and which the safe-mode sweep covers.
# Phone and email are absent deliberately: neither has a checksum, so including
# them would let a sweep pass on engines it never actually examined.
CHECKSUMMED: dict[str, ModuleType] = {
    "TCKN": tckn,
    "VKN": vkn,
    "IBAN": iban,
    "PAN": pan,
}

ALL_ENGINES: dict[str, ModuleType] = {
    **CHECKSUMMED,
    "PHONE": phone,
    "EMAIL": email,
}

__all__ = [
    "ALL_ENGINES",
    "CHECKSUMMED",
    "IdentifierPolicy",
    "email",
    "fold",
    "fold_for_local_part",
    "iban",
    "pan",
    "parse_policy",
    "phone",
    "tckn",
    "vkn",
]
