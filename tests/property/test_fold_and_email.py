"""Folding preserves length, and every address stays inside reserved names.

The length property is not cosmetic. Label spans are code point offsets into the
emitted text, so a fold that grows a string by one code point shifts every span
after it. Python's own `str.lower()` does exactly that to `İ`, which is why this
project folds explicitly rather than calling it.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mintmark.engine.prng import SplitMix64
from mintmark.identifiers import IdentifierPolicy, email, fold, fold_for_local_part

TURKISH_ALPHABET = "abcçdefgğhıijklmnoöprsştuüvyzABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ"

turkish_text = st.text(alphabet=TURKISH_ALPHABET, min_size=0, max_size=40)
QUICK = settings(max_examples=400, deadline=None)


def test_python_lower_is_wrong_for_turkish_which_is_why_this_module_exists() -> None:
    """Documents the bug being avoided, so nobody 'simplifies' the fold away."""
    assert len("İ".lower()) == 2, "str.lower() no longer expands dotted capital I"
    assert "I".lower() == "i"
    # The fold does neither of those things.
    assert fold("İ") == "i"
    assert len(fold("İ")) == 1


@QUICK
@given(text=turkish_text)
def test_fold_never_changes_code_point_count(text: str) -> None:
    assert len(fold(text)) == len(text)


@QUICK
@given(text=turkish_text)
def test_fold_is_idempotent(text: str) -> None:
    once = fold(text)
    assert fold(once) == once


@QUICK
@given(text=turkish_text)
def test_fold_output_is_ascii_for_turkish_input(text: str) -> None:
    assert fold(text).isascii()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("İstanbul", "istanbul"),
        ("ILGAZ", "ilgaz"),
        ("Işık", "isik"),
        ("Gülşen", "gulsen"),
        ("Çağrı", "cagri"),
        ("Öztürk", "ozturk"),
        ("ŞAHİN", "sahin"),
        ("Ğğ", "gg"),
    ],
)
def test_known_turkish_foldings(source: str, expected: str) -> None:
    assert fold(source) == expected


def test_local_part_folding_drops_only_non_alphanumerics() -> None:
    assert fold_for_local_part("Ayşe-Nur") == "aysenur"
    assert fold_for_local_part("O'Brien") == "obrien"
    assert fold_for_local_part("...") == ""


def test_local_part_derivation_joins_with_a_dot() -> None:
    assert email.derive_local_part("Ayşe", "Yılmaz") == "ayse.yilmaz"


def test_name_that_folds_to_nothing_falls_back_rather_than_emitting_an_empty_local() -> None:
    assert email.derive_local_part("...", "---") == "kullanici"


def test_every_generated_address_sits_under_a_reserved_name() -> None:
    """RFC 2606 and RFC 6761: these names can never be registered by anyone."""
    stream = SplitMix64(20260822)
    for _ in range(4000):
        address = email.generate(
            stream, IdentifierPolicy.SAFE, first_name="Ayşe", last_name="Yılmaz"
        )
        assert email.is_reserved(address), f"escaped the reserved space: {address}"


def test_employer_subdomain_stays_inside_the_reserved_tld() -> None:
    stream = SplitMix64(7)
    address = email.generate(
        stream,
        IdentifierPolicy.SAFE,
        first_name="Ayşe",
        last_name="Yılmaz",
        subdomain="Anka Holding",
    )
    assert address.endswith("@ankaholding.example")
    assert email.is_reserved(address)


def test_generated_addresses_are_ascii_and_contain_exactly_one_at_sign() -> None:
    stream = SplitMix64(3)
    for _ in range(1000):
        address = email.generate(
            stream, IdentifierPolicy.SAFE, first_name="Çiğdem", last_name="Şahin"
        )
        assert address.isascii()
        assert address.count("@") == 1


def test_addresses_disambiguate_identical_folded_names() -> None:
    """Two people whose names fold identically must not share an address."""
    stream = SplitMix64(41)
    addresses = {
        email.generate(stream, IdentifierPolicy.SAFE, first_name="Ali", last_name="Yilmaz")
        for _ in range(200)
    }
    assert len(addresses) > 150, "addresses collide far more often than the suffix should allow"


@pytest.mark.parametrize(
    "address",
    ["ali@gmail.com", "ali@example.com.tr", "ali@ornek.com", "ali@examples.com", "no-at-sign"],
)
def test_non_reserved_addresses_are_recognized_as_such(address: str) -> None:
    assert not email.is_reserved(address)


def test_engines_without_a_checksum_report_no_valid_values() -> None:
    """Keeps the safe-mode sweep honest.

    A sweep asserting "zero checksum-valid values" must not be satisfiable by an
    engine that has no checksum, so these report False rather than True.
    """
    from mintmark.identifiers import phone

    assert not phone.is_checksum_valid("+90 555 123 45 67")
    assert not email.is_checksum_valid("a.b.1@example.com")


def test_phone_numbers_match_the_documented_format() -> None:
    from mintmark.identifiers import phone

    stream = SplitMix64(53)
    for _ in range(2000):
        value = phone.generate(stream, IdentifierPolicy.SAFE)
        assert phone.is_well_formed(value), value
        assert value.startswith("+90 5")
        assert len(phone.compact(value)) == 13
