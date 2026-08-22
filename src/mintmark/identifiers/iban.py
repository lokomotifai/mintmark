"""IBAN in its Turkish form, twenty-six characters.

    TR | 2 check digits | 5-digit bank code | 1 reserved zero | 16-digit account

Check digits follow MOD 97-10 of ISO 7064: move the first four characters to the
end, map letters to numbers with A=10 through Z=35, take the remainder modulo 97,
and subtract it from 98. Valid check digits therefore lie in 02 through 98.

Both policies use the bank code 99999. That this code is unassigned was verified
at implementation time against the TCMB payment systems participant list, which
allocates four-digit codes in the range 0001 through 0807 across 71 participants
and contains nothing in the 9xxxx range. The record is in
`docs/normative-verification.md`.

The consequence is worth stating plainly, because it is what makes validator mode
defensible: a validator-policy IBAN from this engine is checksum-valid and still
unroutable, because no institution holds the bank code it names.
"""

from __future__ import annotations

from mintmark.engine.draws import bounded, bounded_range
from mintmark.engine.prng import SplitMix64
from mintmark.identifiers.policy import IdentifierPolicy

COUNTRY = "TR"
LENGTH = 26
LABEL = "IBAN"

# Verified unassigned against the TCMB participant list. See the module docstring.
FICTIONAL_BANK_CODE = "99999"
RESERVED_DIGIT = "0"

_ACCOUNT_DIGITS = 16
_CHECK_LOW, _CHECK_HIGH = 2, 98
_CHECK_SPAN = _CHECK_HIGH - _CHECK_LOW + 1  # 97 admissible check values


def _numeric_form(country: str, check: str, body: str) -> int:
    """Rearrange and letter-map an IBAN into the integer MOD 97-10 operates on."""
    rearranged = f"{body}{country}{check}"
    digits: list[str] = []
    for character in rearranged:
        if character.isdigit():
            digits.append(character)
        else:
            digits.append(str(ord(character.upper()) - ord("A") + 10))
    return int("".join(digits))


def _correct_check(body: str) -> int:
    """The check digits that would make `body` a valid TR IBAN."""
    return 98 - (_numeric_form(COUNTRY, "00", body) % 97)


def generate(stream: SplitMix64, policy: IdentifierPolicy) -> str:
    """Emit one Turkish IBAN under the given policy, in plain form."""
    account = "".join(str(bounded(stream, 10)) for _ in range(_ACCOUNT_DIGITS))
    body = f"{FICTIONAL_BANK_CODE}{RESERVED_DIGIT}{account}"
    check = _correct_check(body)

    if policy is IdentifierPolicy.SAFE:
        # Shift within the admissible 02..98 window by a nonzero offset, so the
        # result stays a plausible IBAN shape and is never the correct value.
        offset = bounded_range(stream, 1, _CHECK_SPAN - 1)
        check = ((check - _CHECK_LOW + offset) % _CHECK_SPAN) + _CHECK_LOW

    return f"{COUNTRY}{check:02d}{body}"


def group(value: str) -> str:
    """Render an IBAN in the space-grouped form banks print, blocks of four."""
    compact = value.replace(" ", "")
    return " ".join(compact[i : i + 4] for i in range(0, len(compact), 4))


def is_checksum_valid(value: str) -> bool:
    """Return True when `value` is a well-formed, checksum-valid TR IBAN.

    Accepts either the plain or the space-grouped form, because both are emitted
    and a verifier must catch a valid checksum in whichever one it meets.
    """
    compact = value.replace(" ", "")
    if len(compact) != LENGTH:
        return False
    if not compact.startswith(COUNTRY):
        return False
    if not compact[2:].isdigit():
        return False
    check = compact[2:4]
    if not _CHECK_LOW <= int(check) <= _CHECK_HIGH:
        return False
    return _numeric_form(COUNTRY, check, compact[4:]) % 97 == 1
