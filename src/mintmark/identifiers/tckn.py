"""TCKN, the Turkish national identity number.

Eleven digits. The first may not be zero. Two public check rules govern the last
two digits:

    d10 = ((d1 + d3 + d5 + d7 + d9) * 7 - (d2 + d4 + d6 + d8)) mod 10
    d11 = (d1 + d2 + ... + d10) mod 10

Safe mode computes both correctly and then corrupts d11 by a nonzero offset. The
result always fails the second rule while still passing the first, which makes it
format-plausible to a human reader and unambiguously invalid to any validator.
Corrupting d11 rather than an earlier digit is deliberate: it leaves the number's
visible shape untouched and puts the invalidity in exactly the place a checker
looks.
"""

from __future__ import annotations

from mintmark.engine.draws import bounded, bounded_range
from mintmark.engine.prng import SplitMix64
from mintmark.identifiers.policy import IdentifierPolicy

LENGTH = 11
LABEL = "TCKN"


def _check_digits(first9: str) -> tuple[int, int]:
    digits = [int(c) for c in first9]
    odd_sum = digits[0] + digits[2] + digits[4] + digits[6] + digits[8]
    even_sum = digits[1] + digits[3] + digits[5] + digits[7]
    d10 = (odd_sum * 7 - even_sum) % 10
    d11 = (sum(digits) + d10) % 10
    return d10, d11


def generate(stream: SplitMix64, policy: IdentifierPolicy) -> str:
    """Emit one TCKN under the given policy."""
    first = bounded_range(stream, 1, 9)
    rest = [bounded(stream, 10) for _ in range(8)]
    first9 = str(first) + "".join(str(d) for d in rest)

    d10, d11 = _check_digits(first9)
    if policy is IdentifierPolicy.SAFE:
        # A nonzero offset guarantees the second rule fails.
        d11 = (d11 + bounded_range(stream, 1, 9)) % 10
    return f"{first9}{d10}{d11}"


def is_checksum_valid(value: str) -> bool:
    """Return True when `value` satisfies both published check rules.

    This is the same function `verify` runs over every emitted file under a safe
    policy, so an engine cannot declare itself safe: it has to survive the check
    a consumer would apply.
    """
    if len(value) != LENGTH or not value.isdigit():
        return False
    if value[0] == "0":
        return False
    d10, d11 = _check_digits(value[:9])
    return value[9] == str(d10) and value[10] == str(d11)
