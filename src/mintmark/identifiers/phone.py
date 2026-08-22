"""Turkish mobile numbers, in the format +90 5XX XXX XX XX.

There is no reserved fictional mobile range in the Turkish numbering plan. Unlike
the +44 7700 900xxx block in the United Kingdom or the 555-0100 range in North
America, there is no span of numbers guaranteed never to be assigned. A generated
number can therefore coincide with an assigned one.

That limitation cannot be engineered away, so it is documented instead: both
READMEs state it, and they state the purpose limitation that follows from it.
This data is for testing systems. It is never for contacting anyone.
"""

from __future__ import annotations

from mintmark.engine.draws import bounded
from mintmark.engine.prng import SplitMix64
from mintmark.identifiers.policy import IdentifierPolicy

LABEL = "PHONE"
COUNTRY_CODE = "+90"

# Turkish mobile numbers begin with 5, then an operator prefix digit pair.
_MOBILE_PREFIX = "5"


def generate(stream: SplitMix64, policy: IdentifierPolicy) -> str:
    """Emit one Turkish mobile number.

    The policy is accepted for interface symmetry and is deliberately unused: a
    phone number carries no checksum, so there is no valid or invalid form to
    choose between. Pretending otherwise would suggest a safety property this
    engine does not have.
    """
    del policy
    subscriber = "".join(str(bounded(stream, 10)) for _ in range(9))
    area = _MOBILE_PREFIX + subscriber[:2]
    return f"{COUNTRY_CODE} {area} {subscriber[2:5]} {subscriber[5:7]} {subscriber[7:9]}"


def compact(value: str) -> str:
    """Strip formatting, leaving the country code and digits."""
    return value.replace(" ", "")


def is_checksum_valid(value: str) -> bool:
    """Phone numbers carry no checksum, so there is nothing to be valid.

    Returning False unconditionally is the honest answer, and it keeps the
    safe-mode sweep meaningful: a sweep asserting "zero checksum-valid values"
    must not be satisfied by an engine that has no checksum to begin with.
    """
    del value
    return False


def is_well_formed(value: str) -> bool:
    """Return True when `value` matches the emitted format exactly."""
    parts = value.split(" ")
    if len(parts) != 5 or parts[0] != COUNTRY_CODE:
        return False
    if not parts[1].startswith(_MOBILE_PREFIX):
        return False
    lengths = [3, 3, 2, 2]
    return all(p.isdigit() and len(p) == n for p, n in zip(parts[1:], lengths, strict=True))
