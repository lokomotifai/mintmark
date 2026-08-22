"""Invariant 2: safe-mode output contains zero checksum-valid identifiers.

This is the invariant the product's safety claim rests on. A safe-mode value must
be provably unable to belong to any real person or account, and the proof is not
that the corruption step ran. It is that the value fails the same validator a
consumer would apply.

Each engine is therefore swept twice: safe mode must never produce a valid value,
and validator mode must always produce one. The second half matters as much as the
first. An engine whose validator mode also produced invalid values would pass a
naive safety sweep while being broken.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mintmark.engine.prng import SplitMix64
from mintmark.identifiers import CHECKSUMMED, IdentifierPolicy, iban, pan, tckn, vkn

SWEEP = 4000
ENGINE_IDS = sorted(CHECKSUMMED)

DEEP = settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@pytest.mark.parametrize("name", ENGINE_IDS)
def test_safe_mode_produces_no_checksum_valid_value(name: str) -> None:
    engine = CHECKSUMMED[name]
    stream = SplitMix64(20260822)
    offenders: list[str] = []
    for _ in range(SWEEP):
        value = engine.generate(stream, IdentifierPolicy.SAFE)
        if engine.is_checksum_valid(value):
            offenders.append(value)
    assert not offenders, (
        f"{name} safe mode produced {len(offenders)} checksum-valid value(s), "
        f"first: {offenders[0]}. Safe mode is the product's safety claim."
    )


@pytest.mark.parametrize("name", ENGINE_IDS)
def test_validator_mode_always_produces_a_checksum_valid_value(name: str) -> None:
    engine = CHECKSUMMED[name]
    stream = SplitMix64(20260823)
    for index in range(SWEEP):
        value = engine.generate(stream, IdentifierPolicy.VALIDATOR)
        assert engine.is_checksum_valid(value), f"{name} validator mode failed at draw {index}"


@DEEP
@given(seed=st.integers(0, (1 << 64) - 1))
@pytest.mark.parametrize("name", ENGINE_IDS)
def test_safe_mode_purity_holds_from_any_seed(name: str, seed: int) -> None:
    """A safety property that only holds for the seeds we tried is not a property."""
    engine = CHECKSUMMED[name]
    stream = SplitMix64(seed)
    for _ in range(16):
        assert not engine.is_checksum_valid(engine.generate(stream, IdentifierPolicy.SAFE))


def test_vkn_reproduces_the_published_verification_vector() -> None:
    """The vector from python-stdnum, which the algorithm was verified against.

    4540536920 is documented as valid and 4540536921 as an invalid checksum. If
    this ever fails, the algorithm drifted from the one that was verified, and
    the safety argument in docs/normative-verification.md no longer describes
    the code.
    """
    assert vkn.is_checksum_valid("4540536920")
    assert not vkn.is_checksum_valid("4540536921")


def test_tckn_first_check_rule_survives_safe_corruption() -> None:
    """Safe mode corrupts the second rule only, leaving the shape plausible."""
    stream = SplitMix64(5)
    for _ in range(500):
        value = tckn.generate(stream, IdentifierPolicy.SAFE)
        digits = [int(c) for c in value]
        odd = digits[0] + digits[2] + digits[4] + digits[6] + digits[8]
        even = digits[1] + digits[3] + digits[5] + digits[7]
        assert digits[9] == (odd * 7 - even) % 10, "the first check rule was disturbed"
        assert not tckn.is_checksum_valid(value)


def test_tckn_never_starts_with_zero() -> None:
    stream = SplitMix64(11)
    for policy in IdentifierPolicy:
        for _ in range(1000):
            assert tckn.generate(stream, policy)[0] != "0"


def test_iban_safe_check_digits_stay_inside_the_admissible_window() -> None:
    """Corruption must not push the check digits outside 02..98.

    A value of 00, 01, or 99 would be rejected on format rather than on
    checksum, which would make the safe value obviously synthetic to a parser
    and, worse, would let a lenient parser skip the checksum entirely.
    """
    stream = SplitMix64(13)
    for _ in range(4000):
        value = iban.generate(stream, IdentifierPolicy.SAFE)
        assert 2 <= int(value[2:4]) <= 98, f"check digits out of range: {value}"


def test_iban_always_carries_the_fictional_bank_code() -> None:
    """Verified unassigned against the TCMB participant list."""
    stream = SplitMix64(17)
    for policy in IdentifierPolicy:
        for _ in range(500):
            assert iban.generate(stream, policy)[4:9] == iban.FICTIONAL_BANK_CODE


def test_validator_iban_is_checksum_valid_yet_unroutable() -> None:
    """The property that makes validator mode defensible, asserted directly."""
    stream = SplitMix64(19)
    for _ in range(500):
        value = iban.generate(stream, IdentifierPolicy.VALIDATOR)
        assert iban.is_checksum_valid(value)
        assert value[4:9] == "99999", "a checksum-valid IBAN must still name no real bank"


def test_iban_grouped_form_validates_the_same_as_the_plain_form() -> None:
    stream = SplitMix64(23)
    for _ in range(500):
        plain = iban.generate(stream, IdentifierPolicy.VALIDATOR)
        assert iban.is_checksum_valid(iban.group(plain))
        assert iban.group(plain).replace(" ", "") == plain


def test_pan_always_begins_with_the_unused_industry_identifier() -> None:
    """Holds under both policies, which invalid checksums alone cannot promise."""
    stream = SplitMix64(29)
    for policy in IdentifierPolicy:
        for _ in range(1000):
            assert pan.generate(stream, policy)[0] == "9"


def test_pan_masking_hides_the_middle_and_keeps_the_length() -> None:
    stream = SplitMix64(31)
    value = pan.generate(stream, IdentifierPolicy.SAFE)
    masked = pan.mask(value)
    assert len(masked) == 16
    assert masked[:6] == value[:6]
    assert masked[6:12] == "******"
    assert masked[-4:] == value[-4:]


def test_masking_a_wrong_length_value_is_refused() -> None:
    with pytest.raises(ValueError, match="16-digit PAN"):
        pan.mask("123")
