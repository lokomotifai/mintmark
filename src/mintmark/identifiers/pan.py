"""Card PAN, sixteen digits with a Luhn check.

The first digit is 9. The major industry identifier 9 is reserved for national
assignment and is not used by any commercial card network, so a PAN from this
engine cannot be mistaken for a real card number by its prefix alone. That is a
stronger guarantee than an invalid checksum on its own: it holds even for the
validator policy, where the checksum is deliberately correct.

Default emission is masked. A full PAN is emitted only where a recipe explicitly
asks for one, because a dataset that spreads full card numbers by default invites
exactly the handling mistakes synthetic data exists to avoid.
"""

from __future__ import annotations

from mintmark.engine.draws import bounded, bounded_range
from mintmark.engine.prng import SplitMix64
from mintmark.identifiers.policy import IdentifierPolicy

LENGTH = 16
LABEL = "PAN"

# Major industry identifier 9: reserved for national assignment, unused by the
# commercial card networks.
LEADING_DIGIT = "9"

_MASK_PREFIX = 6
_MASK_SUFFIX = 4


def _luhn_check_digit(first15: str) -> int:
    total = 0
    # Positions are counted from the right of the completed number, so the digit
    # adjacent to the check digit is doubled.
    for position, character in enumerate(reversed(first15)):
        digit = int(character)
        if position % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return (10 - (total % 10)) % 10


def generate(stream: SplitMix64, policy: IdentifierPolicy) -> str:
    """Emit one full PAN under the given policy."""
    body = LEADING_DIGIT + "".join(str(bounded(stream, 10)) for _ in range(LENGTH - 2))
    check = _luhn_check_digit(body)
    if policy is IdentifierPolicy.SAFE:
        check = (check + bounded_range(stream, 1, 9)) % 10
    return f"{body}{check}"


def mask(value: str) -> str:
    """Render a PAN in the masked form a statement or a support tool shows."""
    if len(value) != LENGTH:
        raise ValueError(f"expected a {LENGTH}-digit PAN, got {len(value)} characters")
    hidden = "*" * (LENGTH - _MASK_PREFIX - _MASK_SUFFIX)
    return f"{value[:_MASK_PREFIX]}{hidden}{value[-_MASK_SUFFIX:]}"


def is_checksum_valid(value: str) -> bool:
    """Return True when `value` is sixteen digits satisfying the Luhn check."""
    if len(value) != LENGTH or not value.isdigit():
        return False
    return int(value[15]) == _luhn_check_digit(value[:15])


def is_well_formed(value: str) -> bool:
    """Return True when `value` is a full sixteen-digit PAN or its masked form."""
    if len(value) != LENGTH:
        return False
    if value.isdigit():
        return True
    prefix, hidden, suffix = (
        value[:_MASK_PREFIX],
        value[_MASK_PREFIX : LENGTH - _MASK_SUFFIX],
        value[LENGTH - _MASK_SUFFIX :],
    )
    return prefix.isdigit() and suffix.isdigit() and hidden == "*" * len(hidden)
