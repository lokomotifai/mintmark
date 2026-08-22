"""The closed label set, pinned by digest.

Eighteen labels: the twelve named-entity types of the hushmark-tr closed v0.1 set,
plus the six deterministic identifier labels this project emits.

The set is closed. An unknown label anywhere fails closed: pack loading rejects it
with exit code 2, and `verify` rejects it with exit code 3. That strictness is what
makes a Mintmark dataset usable as an evaluation set. A detector scored against a
label the taxonomy never defined produces a number that means nothing, and the
failure is silent unless something refuses the label outright.

The pin is a digest over the canonical label list. It is recorded in every manifest
so that a dataset stays interpretable after upstream moves, and it is computed
locally so that verification needs no network. Checking the pin against upstream is
a cadence concern, not a mint-time one, and drift opens an issue rather than
re-pinning automatically: a taxonomy change alters what every published dataset
means, so it is a decision rather than an update.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum

TAXONOMY_NAME = "hushmark-tr"
TAXONOMY_VERSION = "0.1"


class Label(StrEnum):
    """Every label a span may carry. The set is closed and ordered."""

    # The twelve named-entity types, in the order the upstream label map declares
    # them. Order is part of the pin, so it is preserved rather than sorted.
    PERSON = "PERSON"
    ADDRESS = "ADDRESS"
    ORG = "ORG"
    DOB = "DOB"
    HEALTH = "HEALTH"
    RELIGION = "RELIGION"
    ETHNICITY = "ETHNICITY"
    POLITICAL = "POLITICAL"
    SEXUAL_LIFE = "SEXUAL_LIFE"
    CRIMINAL = "CRIMINAL"
    BIOMETRIC_REF = "BIOMETRIC_REF"
    UNION = "UNION"

    # The six deterministic identifier labels.
    TCKN = "TCKN"
    VKN = "VKN"
    IBAN = "IBAN"
    PAN = "PAN"
    PHONE = "PHONE"
    EMAIL = "EMAIL"


# The twelve upstream types, separated from the identifier labels because the pin
# covers the upstream set and coverage targets are stated per group.
NER_LABELS: tuple[Label, ...] = (
    Label.PERSON,
    Label.ADDRESS,
    Label.ORG,
    Label.DOB,
    Label.HEALTH,
    Label.RELIGION,
    Label.ETHNICITY,
    Label.POLITICAL,
    Label.SEXUAL_LIFE,
    Label.CRIMINAL,
    Label.BIOMETRIC_REF,
    Label.UNION,
)

DETERMINISTIC_LABELS: tuple[Label, ...] = (
    Label.TCKN,
    Label.VKN,
    Label.IBAN,
    Label.PAN,
    Label.PHONE,
    Label.EMAIL,
)

# The eight labels that carry special-category personal data. Named here so that
# a pack's special-category rate has one definition rather than a list repeated
# in every recipe.
SPECIAL_CATEGORY_LABELS: tuple[Label, ...] = (
    Label.HEALTH,
    Label.RELIGION,
    Label.ETHNICITY,
    Label.POLITICAL,
    Label.SEXUAL_LIFE,
    Label.CRIMINAL,
    Label.BIOMETRIC_REF,
    Label.UNION,
)

ALL_LABELS: tuple[Label, ...] = NER_LABELS + DETERMINISTIC_LABELS


class UnknownLabelError(ValueError):
    """A label outside the closed set was encountered."""


def parse_label(value: str) -> Label:
    """Return the Label for `value`, failing closed on anything else."""
    try:
        return Label(value)
    except ValueError:
        raise UnknownLabelError(
            f"unknown label {value!r}. The taxonomy is closed at "
            f"{TAXONOMY_NAME} v{TAXONOMY_VERSION}; allowed labels are: "
            + ", ".join(label.value for label in ALL_LABELS)
        ) from None


def pin_digest() -> str:
    """The digest recorded in every manifest.

    Computed over the canonical NER label list, newline separated, so that it
    depends on the upstream set and not on this project's identifier labels,
    which are ours to change without upstream involvement.
    """
    canonical = "\n".join(label.value for label in NER_LABELS) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def pin() -> dict[str, str]:
    """The taxonomy block as it appears in a manifest."""
    return {
        "name": TAXONOMY_NAME,
        "version": TAXONOMY_VERSION,
        "pin_digest": pin_digest(),
    }
