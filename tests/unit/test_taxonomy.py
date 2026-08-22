"""Invariant 10: the taxonomy is closed, and its pin is stable.

The pin is what keeps a published dataset interpretable after upstream moves. It
is asserted against a literal digest here, so that a change to the label set
cannot slip through as an ordinary edit: changing what a dataset means is a
decision, and this test forces it to be made deliberately.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mintmark.annotate import (
    ALL_LABELS,
    DETERMINISTIC_LABELS,
    NER_LABELS,
    SPECIAL_CATEGORY_LABELS,
    TAXONOMY_NAME,
    TAXONOMY_VERSION,
    Label,
    UnknownLabelError,
    parse_label,
    pin,
    pin_digest,
)

# The twelve upstream types, transcribed from the hushmark label map on
# 2026-08-22 and recorded in docs/normative-verification.md.
UPSTREAM_NER = (
    "PERSON",
    "ADDRESS",
    "ORG",
    "DOB",
    "HEALTH",
    "RELIGION",
    "ETHNICITY",
    "POLITICAL",
    "SEXUAL_LIFE",
    "CRIMINAL",
    "BIOMETRIC_REF",
    "UNION",
)


def test_the_ner_set_matches_the_verified_upstream_set_exactly() -> None:
    assert tuple(label.value for label in NER_LABELS) == UPSTREAM_NER


def test_the_set_is_closed_at_eighteen_labels() -> None:
    assert len(ALL_LABELS) == 18
    assert len(NER_LABELS) == 12
    assert len(DETERMINISTIC_LABELS) == 6
    assert set(ALL_LABELS) == set(Label)


def test_special_category_labels_are_the_eight_that_carry_sensitive_data() -> None:
    assert len(SPECIAL_CATEGORY_LABELS) == 8
    assert set(SPECIAL_CATEGORY_LABELS) <= set(NER_LABELS)
    assert Label.PERSON not in SPECIAL_CATEGORY_LABELS
    assert Label.ADDRESS not in SPECIAL_CATEGORY_LABELS


def test_pin_digest_is_stable() -> None:
    """A changed digest means the label set changed, which changes every dataset.

    If this fails, do not update the literal to make it pass. Decide whether the
    taxonomy should have changed, record the decision, and treat it as a major
    version event.
    """
    assert pin_digest() == "af11b31e4916e9d4dcedfd103bf9625d87f0927ae17bbefad1a95255c6be383a"


def test_pin_block_carries_name_version_and_digest() -> None:
    block = pin()
    assert block == {
        "name": TAXONOMY_NAME,
        "version": TAXONOMY_VERSION,
        "pin_digest": pin_digest(),
    }
    assert block["name"] == "hushmark-tr"
    assert block["version"] == "0.1"


def test_pin_covers_only_the_upstream_set() -> None:
    """The identifier labels are ours; upstream drift must not depend on them."""
    import hashlib

    expected = hashlib.sha256(("\n".join(UPSTREAM_NER) + "\n").encode("utf-8")).hexdigest()
    assert pin_digest() == expected


@pytest.mark.parametrize("value", [label.value for label in ALL_LABELS])
def test_every_known_label_parses(value: str) -> None:
    assert parse_label(value).value == value


@pytest.mark.parametrize(
    "value",
    ["PLATE", "person", "Person", "NAME", "SSN", "", "PERSON ", "UNKNOWN"],
)
def test_an_unknown_label_fails_closed(value: str) -> None:
    with pytest.raises(UnknownLabelError, match="unknown label"):
        parse_label(value)


def test_the_rejection_message_names_the_allowed_set() -> None:
    """A fail-closed error is only useful if it says what would have worked."""
    with pytest.raises(UnknownLabelError) as caught:
        parse_label("PLATE")
    message = str(caught.value)
    assert "hushmark-tr" in message
    assert "PERSON" in message
    assert "BIOMETRIC_REF" in message


def test_there_is_no_plate_label() -> None:
    """The insurance pack emits vehicle plates unlabeled because of this.

    Recorded as a test so that adding a PLATE label is a deliberate act with a
    visible consequence, rather than a convenience someone reaches for while
    writing a pack.
    """
    assert "PLATE" not in {label.value for label in ALL_LABELS}


def test_the_verification_record_documents_the_taxonomy_source() -> None:
    record = Path(__file__).resolve().parents[2] / "docs" / "normative-verification.md"
    text = record.read_text(encoding="utf-8")
    assert "hushmark-tr" in text
