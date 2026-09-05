"""Every identifier engine can recognize the shape of what it emits.

`verify` applies these to every span carrying an identifier label, so a
sidecar whose offsets drifted cannot keep the label on a fragment. Shape is not
validity: a safe-mode value and a validator-mode value must both pass.
"""

from __future__ import annotations

import pytest

from mintmark.engine.prng import SplitMix64
from mintmark.identifiers import ALL_ENGINES, IdentifierPolicy, email, iban, pan


@pytest.mark.parametrize("name", sorted(ALL_ENGINES))
@pytest.mark.parametrize("policy", [IdentifierPolicy.SAFE, IdentifierPolicy.VALIDATOR])
def test_every_emitted_value_is_well_formed(name: str, policy: IdentifierPolicy) -> None:
    engine = ALL_ENGINES[name]
    stream = SplitMix64(11)
    for _ in range(300):
        if name == "EMAIL":
            value = engine.generate(stream, policy, first_name="Ayşe", last_name="Öztürk")
        else:
            value = engine.generate(stream, policy)
        assert engine.is_well_formed(value), (name, value)


@pytest.mark.parametrize(
    ("name", "fragment"),
    [
        ("TCKN", "1773625043"),
        ("TCKN", "01773625043"),
        ("VKN", "710786625"),
        ("IBAN", "R069999903275422876779493"),
        ("IBAN", "TR06 9999 9032 7542 2876 7794 93 "),
        ("PAN", "55274******9455"),
        ("PAN", "955274*****94555"),
        ("PHONE", "90 525 886 73 05"),
        ("EMAIL", "kaan.kilic.1256@gmail.com"),
        ("EMAIL", "@example.org"),
    ],
)
def test_a_shifted_or_foreign_surface_is_not_well_formed(name: str, fragment: str) -> None:
    assert not ALL_ENGINES[name].is_well_formed(fragment)


def test_both_iban_renderings_are_well_formed() -> None:
    plain = "TR069999903275422876779493"
    assert iban.is_well_formed(plain)
    assert iban.is_well_formed(iban.group(plain))


def test_a_masked_and_a_full_pan_are_both_well_formed() -> None:
    full = "9552740000009455"
    assert pan.is_well_formed(full)
    assert pan.is_well_formed(pan.mask(full))


def test_email_shape_requires_a_reserved_domain() -> None:
    assert email.is_well_formed("ayse.ozturk.1@example.com")
    assert email.is_well_formed("ayse@ornek.example")
    assert not email.is_well_formed("ayse.ozturk.1@example.co")
