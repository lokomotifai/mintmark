"""Rendering places spans as it writes, and every span re-extracts.

The alternative implementation, searching the finished text for each value, is
what these tests rule out. It finds the wrong occurrence whenever a value appears
twice, and a document that names the same person in two sentences is ordinary
rather than exceptional.
"""

from __future__ import annotations

import pytest

from mintmark.annotate import Label, RenderError, Resolvers, render
from mintmark.engine.prng import SplitMix64
from mintmark.engine.templates import parse_template

LABELS = frozenset(label.value for label in Label)
IDENTIFIERS = frozenset({"TCKN", "VKN", "IBAN", "PAN", "PHONE", "EMAIL"})

GRAPH = {
    "customer.first_name": "Ayşe",
    "customer.last_name": "Yılmaz",
    "customer.city": "Eskişehir",
    "customer.note": None,
    "customer.blank": "",
    "account.type": "vadesiz",
}

FIELD_LABELS = {
    "customer.first_name": Label.PERSON,
    "customer.last_name": Label.PERSON,
    "customer.city": Label.ADDRESS,
}

DESCRIPTORS = {
    Label.HEALTH: "kronik rahatsizlik",
    Label.UNION: "Dayanisma Sendikasi",
    Label.ORG: "Anka Lojistik",
    Label.PERSON: "Mehmet Demir",
}


def resolvers() -> Resolvers:
    return Resolvers(
        field=lambda path: GRAPH.get(path, f"<{path}>"),
        entity=lambda label, _stream: DESCRIPTORS.get(label, f"<{label.value}>"),
        identifier=lambda kind, _stream: {
            "IBAN": "TR990000000000000000000001",
            "TCKN": "10000000146",
            "PAN": "9000001234567890",
            "PHONE": "+90 555 111 22 33",
            "EMAIL": "a.b.1@example.com",
            "VKN": "1234567890",
        }[kind],
        field_label=FIELD_LABELS.get,
    )


def run(text: str, seed: int = 42) -> tuple[str, list]:
    nodes = parse_template(
        text, template_id="t", known_labels=LABELS, known_identifiers=IDENTIFIERS
    )
    return render(nodes, stream=SplitMix64(seed), resolvers=resolvers())


def test_a_labeled_field_produces_a_span_that_re_extracts() -> None:
    text, spans = run("Sayin {field:customer.first_name} {field:customer.last_name},")
    assert text == "Sayin Ayşe Yılmaz,"
    assert [s.extract(text) for s in spans] == ["Ayşe", "Yılmaz"]
    assert all(s.label is Label.PERSON for s in spans)


def test_the_same_value_twice_produces_two_distinct_spans() -> None:
    """The case that rules out searching the finished text for the value."""
    text, spans = run(
        "{field:customer.first_name} aradi. {field:customer.first_name} tekrar aradi."
    )
    assert len(spans) == 2
    assert spans[0].start != spans[1].start
    assert all(span.extract(text) == "Ayşe" for span in spans)


def test_an_unlabeled_field_produces_no_span() -> None:
    text, spans = run("Hesap turu {field:account.type}.")
    assert "vadesiz" in text
    assert spans == []


def test_a_null_field_renders_as_nothing_rather_than_the_word_none() -> None:
    text, _ = run("Not: {field:customer.note} son.")
    assert "None" not in text
    assert text == "Not: son."


def test_an_empty_field_is_skipped_rather_than_labeled_empty() -> None:
    text, spans = run("Deger {field:customer.blank} bitti.")
    assert text == "Deger bitti."
    assert spans == []


def test_identifier_slots_carry_their_own_label() -> None:
    text, spans = run("IBAN {id:IBAN} ve TCKN {id:TCKN}.")
    assert {span.label for span in spans} == {Label.IBAN, Label.TCKN}
    for span in spans:
        assert span.extract(text)


def test_entity_slots_carry_the_declared_label() -> None:
    text, spans = run("Calisan {entity:HEALTH} nedeniyle izinli.")
    assert len(spans) == 1
    assert spans[0].label is Label.HEALTH
    assert spans[0].extract(text) == "kronik rahatsizlik"


def test_spans_survive_whitespace_collapsing_around_them() -> None:
    text, spans = run("Sayin     {field:customer.first_name}   ,\n\n  hosgeldiniz.")
    assert "  " not in text
    assert spans[0].extract(text) == "Ayşe"


def test_alternation_picks_one_branch_and_only_one() -> None:
    outcomes = {run("(birinci|ikinci|ucuncu) secildi.", seed=s)[0] for s in range(60)}
    assert outcomes <= {"birinci secildi.", "ikinci secildi.", "ucuncu secildi."}
    assert len(outcomes) > 1, "the alternation never varied across sixty seeds"


def test_optional_at_rate_zero_never_appears() -> None:
    for seed in range(40):
        text, _ = run("Temel [?0: asla] son.", seed=seed)
        assert text == "Temel son."


def test_optional_at_rate_one_always_appears() -> None:
    for seed in range(40):
        text, _ = run("Temel [?1: her zaman] son.", seed=seed)
        assert text == "Temel her zaman son."


def test_optional_at_a_middling_rate_varies() -> None:
    outcomes = {run("Temel [?0.5: bazen] son.", seed=s)[0] for s in range(60)}
    assert len(outcomes) == 2


def test_a_span_inside_an_included_optional_still_aligns() -> None:
    text, spans = run("Not: [?1: {entity:UNION} uyeligi] belirtildi.")
    assert len(spans) == 1
    assert spans[0].extract(text) == "Dayanisma Sendikasi"


def test_a_span_inside_an_excluded_optional_is_absent() -> None:
    _, spans = run("Not: [?0: {entity:UNION} uyeligi] belirtildi.")
    assert spans == []


def test_rendering_is_reproducible_from_the_same_seed() -> None:
    template = "({field:customer.first_name}|{entity:PERSON}) [?0.5: ek] {id:PAN}"
    assert run(template, seed=9) == run(template, seed=9)


def test_different_seeds_reach_different_renderings() -> None:
    template = "(a|b|c|d|e|f|g|h) [?0.5: ek]"
    assert len({run(template, seed=s)[0] for s in range(40)}) > 4


def test_an_empty_entity_surface_is_refused() -> None:
    """An empty labeled span would point at nothing while looking like coverage."""
    nodes = parse_template(
        "{entity:HEALTH}", template_id="t", known_labels=LABELS, known_identifiers=IDENTIFIERS
    )
    empty = Resolvers(
        field=lambda _: "",
        entity=lambda _label, _stream: "",
        identifier=lambda _kind, _stream: "",
        field_label=lambda _: None,
    )
    with pytest.raises(RenderError, match="empty surface"):
        render(nodes, stream=SplitMix64(1), resolvers=empty)


def test_literal_braces_reach_the_output() -> None:
    text, _ = run("{{sabit}} deger")
    assert text == "{sabit} deger"


def test_a_long_template_with_many_slots_keeps_every_span_aligned() -> None:
    template = " ".join(
        [
            "Sayin {field:customer.first_name} {field:customer.last_name},",
            "{field:customer.city} subesindeki hesabiniz {id:IBAN} icin",
            "{id:PHONE} numarasindan arandiniz.",
            "[?1: Ayrica {entity:ORG} ile ilgili {entity:HEALTH} notu dusuldu.]",
            "Kart {id:PAN} ve eposta {id:EMAIL}.",
        ]
    )
    text, spans = run(template)
    assert len(spans) == 9
    for span in spans:
        assert span.extract(text), f"span {span} extracts nothing"
    assert spans == sorted(spans)


# The recipe's special_rate, which the template defers to.


def run_special(text: str, rate: str, seed: int = 42) -> tuple[str, list]:
    nodes = parse_template(
        text, template_id="t", known_labels=LABELS, known_identifiers=IDENTIFIERS
    )
    return render(nodes, stream=SplitMix64(seed), resolvers=resolvers(), special_rate=rate)


def test_a_special_segment_is_absent_at_rate_zero() -> None:
    for seed in range(40):
        text, spans = run_special("Not[?special: , {entity:HEALTH} var].", "0", seed)
        assert spans == []
        assert text == "Not."


def test_a_special_segment_is_always_present_at_rate_one() -> None:
    for seed in range(40):
        _, spans = run_special("Not[?special: , {entity:HEALTH} var].", "1", seed)
        assert len(spans) == 1
        assert spans[0].label is Label.HEALTH


def test_the_recipe_rate_actually_governs_the_density() -> None:
    """The point of the deferral: changing the recipe changes the data.

    Before this existed, special_rate was a declared recipe field with no effect.
    The templates decided the density and the recipe only appeared to, so a pack
    author lowering the rate would have changed nothing at all.
    """
    hits = {
        rate: sum(
            1
            for seed in range(400)
            if run_special("Not[?special: , {entity:HEALTH} var].", rate, seed)[1]
        )
        for rate in ("0.05", "0.5", "0.95")
    }
    assert hits["0.05"] < hits["0.5"] < hits["0.95"]
    assert hits["0.05"] < 60
    assert hits["0.95"] > 340


def test_a_literal_rate_still_overrides_nothing() -> None:
    """A template that fixes its own probability keeps it, whatever the recipe says."""
    always = [run_special("A[?1: B]", rate, seed=s)[0] for rate in ("0", "1") for s in range(5)]
    assert set(always) == {"A B"}


def test_the_default_rate_is_zero_rather_than_undeclared() -> None:
    """A caller who forgets the rate gets no special content, not some of it."""
    nodes = parse_template(
        "Not[?special: , {entity:HEALTH} var].",
        template_id="t",
        known_labels=LABELS,
        known_identifiers=IDENTIFIERS,
    )
    _, spans = render(nodes, stream=SplitMix64(1), resolvers=resolvers())
    assert spans == []
