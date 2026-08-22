"""VKN, the Turkish tax identification number.

Ten digits, where the tenth is a check digit over the first nine.

The algorithm below was not taken from this project's own reading of a
specification. It was verified at implementation time against two independent
open implementations, which were then cross-checked against each other over
200 000 random inputs with zero disagreements, and against the published test
vector 4540536920. The verification record, with sources and retrieval date,
lives in `docs/normative-verification.md`.

That care is warranted because the failure mode is silent. A subtly wrong check
digit algorithm still produces ten plausible digits; safe mode would still emit
something, and it would still look fine. What would break is the safety claim
itself: values intended to be provably invalid could land on valid ones.

    s = 0
    for i, digit in enumerate(reversed(first_nine), start=1):
        c1 = (digit + i) mod 10
        if c1 != 0:
            c2 = (c1 * 2**i) mod 9, or 9 when that is zero
            s += c2
    check = (10 - s) mod 10
"""

from __future__ import annotations

from mintmark.engine.draws import bounded, bounded_range
from mintmark.engine.prng import SplitMix64
from mintmark.identifiers.policy import IdentifierPolicy

LENGTH = 10
LABEL = "VKN"


def _check_digit(first9: str) -> int:
    total = 0
    for position, character in enumerate(reversed(first9), start=1):
        shifted = (int(character) + position) % 10
        if shifted:
            # A zero residue maps to 9 rather than dropping out of the sum.
            total += (shifted * (2**position)) % 9 or 9
    return (10 - total) % 10


def generate(stream: SplitMix64, policy: IdentifierPolicy) -> str:
    """Emit one VKN under the given policy."""
    first9 = "".join(str(bounded(stream, 10)) for _ in range(9))
    check = _check_digit(first9)
    if policy is IdentifierPolicy.SAFE:
        check = (check + bounded_range(stream, 1, 9)) % 10
    return f"{first9}{check}"


def is_checksum_valid(value: str) -> bool:
    """Return True when `value` carries the correct check digit."""
    if len(value) != LENGTH or not value.isdigit():
        return False
    return int(value[9]) == _check_digit(value[:9])
