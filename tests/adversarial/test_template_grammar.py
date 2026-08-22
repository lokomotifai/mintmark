"""Malformed templates fail at pack load time, each for its own named rule.

Render-time failure is not an acceptable substitute. A mint writes hundreds of
thousands of records; a template fault discovered on record 90 000 leaves a
half-written output directory and a user who has to work out which of forty
templates was wrong. Parsing at load time turns that into one message before
anything is written.
"""

from __future__ import annotations

import pytest

from mintmark.engine.templates import (
    Alternation,
    EntitySlot,
    FieldSlot,
    IdentifierSlot,
    Literal,
    Optional,
    TemplateError,
    parse_template,
)

LABELS = frozenset({"PERSON", "ORG", "HEALTH", "UNION", "IBAN", "TCKN"})
IDENTIFIERS = frozenset({"TCKN", "VKN", "IBAN", "PAN", "PHONE", "EMAIL"})


def parse(text: str, template_id: str = "fixture") -> tuple[object, ...]:
    return parse_template(
        text, template_id=template_id, known_labels=LABELS, known_identifiers=IDENTIFIERS
    )


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("Sayin {field:customer.first_name", "unbalanced-brace"),
        ("Sayin } yanlis", "unbalanced-brace"),
        ("{customer.first_name}", "malformed-slot"),
        ("{unknown:value}", "unknown-slot-kind"),
        ("{field:}", "empty-slot-argument"),
        ("{entity:PLATE}", "unknown-label"),
        ("{entity:person}", "unknown-label"),
        ("{id:SSN}", "unknown-identifier"),
        ("(sadece bir dal)", "single-branch-alternation"),
        ("(acik|kapali", "unbalanced-paren"),
        ("[?0.3: hic kapanmayan", "unbalanced-bracket"),
        ("[?abc: metin]", "malformed-probability"),
        ("[?1.5: metin]", "probability-out-of-range"),
        ("[?-0.1: metin]", "probability-out-of-range"),
        ("[?NaN: metin]", "probability-out-of-range"),
        ("[0.3: iki soru isareti yok]", "malformed-optional"),
        ("[?0.3 iki nokta yok]", "malformed-optional"),
    ],
)
@pytest.mark.adversarial
def test_malformed_template_is_rejected_by_its_own_rule(text: str, rule: str) -> None:
    with pytest.raises(TemplateError) as caught:
        parse(text)
    assert caught.value.rule == rule, f"rejected as {caught.value.rule!r}, expected {rule!r}"
    assert caught.value.template_id == "fixture"


def test_an_unknown_label_error_names_the_allowed_set() -> None:
    with pytest.raises(TemplateError) as caught:
        parse("{entity:PLATE}")
    assert "PERSON" in str(caught.value)
    assert "closed taxonomy" in str(caught.value)


def test_a_valid_template_parses_into_the_expected_nodes() -> None:
    nodes = parse("Sayin {field:customer.first_name}, (hesap|kart) {id:IBAN}.")
    assert isinstance(nodes[0], Literal)
    assert isinstance(nodes[1], FieldSlot)
    assert nodes[1].path == "customer.first_name"
    assert isinstance(nodes[3], Alternation)
    assert len(nodes[3].branches) == 2
    assert isinstance(nodes[5], IdentifierSlot)


def test_literal_braces_survive_as_text() -> None:
    nodes = parse("{{sabit}} metin")
    assert nodes == (Literal("{sabit} metin"),)


def test_an_optional_can_contain_slots() -> None:
    nodes = parse("[?0.25: ve {entity:UNION} uyeligi]")
    optional = nodes[0]
    assert isinstance(optional, Optional)
    assert optional.rate == "0.25"
    assert any(isinstance(node, EntitySlot) for node in optional.body)


def test_alternation_branches_can_contain_slots() -> None:
    nodes = parse("({field:a.b}|{id:PAN})")
    alternation = nodes[0]
    assert isinstance(alternation, Alternation)
    assert isinstance(alternation.branches[0][0], FieldSlot)
    assert isinstance(alternation.branches[1][0], IdentifierSlot)


def test_nested_optional_inside_an_alternation_parses() -> None:
    nodes = parse("(kisa|uzun [?0.5: ek])")
    alternation = nodes[0]
    assert isinstance(alternation, Alternation)
    assert any(isinstance(node, Optional) for node in alternation.branches[1])


def test_rates_of_exactly_zero_and_one_are_allowed() -> None:
    """The endpoints are how a pack turns a segment fully off or on."""
    assert parse("[?0: hic]")
    assert parse("[?1: her zaman]")


def test_turkish_text_passes_through_unchanged() -> None:
    nodes = parse("Şikâyetiniz değerlendirilmiştir.")
    assert nodes == (Literal("Şikâyetiniz değerlendirilmiştir."),)


def test_an_empty_template_parses_to_nothing() -> None:
    """Rejecting this belongs to the schema's minLength, not to the parser."""
    assert parse("") == ()
