"""The document template grammar, parsed once at pack load time.

    {field:record.path}      a value from the current record graph
    {entity:LABEL}           a draw from the descriptor lexicon for LABEL
    {id:TYPE}                a draw from an identifier engine
    {lex:name}               a draw from a named lexicon, carrying no label
    (a|b|c)                  uniform alternation
    [?0.3: optional text]    included with probability 0.3
    [?special: text]         included at the recipe's special_rate
    {{ and }}                literal braces

Parsing happens when a pack loads, not when a document renders. A template with
an unbalanced brace, an unknown slot type, or a malformed probability is a broken
pack, and a broken pack must fail before a mint starts rather than partway
through writing a hundred thousand records.

The vocabularies of valid labels and identifier types are injected rather than
imported. `engine` imports only the standard library, which is what makes the
determinism claim checkable, so the caller that knows the taxonomy passes it in.
The closure check still happens at load time; only the direction of the
dependency changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from mintmark.engine.draws import boolean, bounded
from mintmark.engine.prng import SplitMix64


class TemplateError(ValueError):
    """A template is malformed. Raised at pack load time, never at render time."""

    def __init__(self, template_id: str, position: int, rule: str, detail: str) -> None:
        self.template_id = template_id
        self.position = position
        self.rule = rule
        self.detail = detail
        super().__init__(f"template {template_id!r} at offset {position}: {rule}: {detail}")


@dataclass(frozen=True, slots=True)
class Literal:
    text: str


@dataclass(frozen=True, slots=True)
class FieldSlot:
    """`{field:customer.first_name}`, resolved against the record graph."""

    path: str


@dataclass(frozen=True, slots=True)
class EntitySlot:
    """`{entity:HEALTH}`, drawn from the descriptor lexicon for that label."""

    label: str


@dataclass(frozen=True, slots=True)
class IdentifierSlot:
    """`{id:IBAN}`, drawn from an identifier engine under the mint's policy."""

    identifier: str


@dataclass(frozen=True, slots=True)
class LexiconSlot:
    """`{lex:perils_tr}`, drawn from a lexicon and emitted without a label.

    Domain vocabulary is not personal data, so it carries no span. It exists so
    that a template can vary its ordinary words instead of repeating one carrier
    sentence, which is what makes a document set worth evaluating against.
    """

    name: str


@dataclass(frozen=True, slots=True)
class Alternation:
    """`(a|b|c)`, uniform over its branches."""

    branches: tuple[tuple[Node, ...], ...]


# A rate of "special" defers to the recipe rather than fixing a number in the
# template. Without it, a recipe's special_rate would be a declared field with no
# effect: the templates would decide the density and the recipe would only appear
# to. A pack author changing the rate would change nothing.
SPECIAL_RATE = "special"


@dataclass(frozen=True, slots=True)
class Optional:
    """`[?0.3: text]`, included with the declared probability.

    The rate is either a decimal string or the literal `special`, which resolves
    to the recipe's special_rate at render time.
    """

    rate: str
    body: tuple[Node, ...]

    @property
    def defers_to_recipe(self) -> bool:
        return self.rate == SPECIAL_RATE


Node = Literal | FieldSlot | EntitySlot | IdentifierSlot | LexiconSlot | Alternation | Optional

_SLOT_KINDS = frozenset({"field", "entity", "id", "lex"})
MAX_TEMPLATE_CHARS = 65_536
MAX_TEMPLATE_DEPTH = 64
MAX_PROBABILITY_DECIMAL_PLACES = 19


def parse_template(
    text: str,
    *,
    template_id: str,
    known_labels: frozenset[str],
    known_identifiers: frozenset[str],
    known_lexicons: frozenset[str] = frozenset(),
) -> tuple[Node, ...]:
    """Compile a template into nodes, failing closed on anything malformed."""
    if len(text) > MAX_TEMPLATE_CHARS:
        raise TemplateError(
            template_id,
            MAX_TEMPLATE_CHARS,
            "template-length-limit",
            f"template exceeds the supported length of {MAX_TEMPLATE_CHARS}",
        )
    nodes, position = _parse_sequence(
        text,
        0,
        template_id=template_id,
        known_labels=known_labels,
        known_identifiers=known_identifiers,
        known_lexicons=known_lexicons,
        terminators="",
        depth=0,
    )
    if position != len(text):
        raise TemplateError(template_id, position, "unexpected-close", f"stray {text[position]!r}")
    return nodes


def _parse_sequence(
    text: str,
    start: int,
    *,
    template_id: str,
    known_labels: frozenset[str],
    known_identifiers: frozenset[str],
    known_lexicons: frozenset[str],
    terminators: str,
    depth: int,
) -> tuple[tuple[Node, ...], int]:
    if depth > MAX_TEMPLATE_DEPTH:
        raise TemplateError(
            template_id,
            start,
            "template-nesting-limit",
            f"template nesting exceeds the supported depth of {MAX_TEMPLATE_DEPTH}",
        )
    nodes: list[Node] = []
    buffer: list[str] = []
    position = start

    def flush() -> None:
        if buffer:
            nodes.append(Literal("".join(buffer)))
            buffer.clear()

    while position < len(text):
        character = text[position]

        if character in terminators:
            break

        if text.startswith("{{", position):
            buffer.append("{")
            position += 2
            continue
        if text.startswith("}}", position):
            buffer.append("}")
            position += 2
            continue

        if character == "{":
            flush()
            node, position = _parse_slot(
                text, position, template_id, known_labels, known_identifiers, known_lexicons
            )
            nodes.append(node)
            continue

        if character == "(":
            flush()
            node, position = _parse_alternation(
                text, position, template_id, known_labels, known_identifiers, known_lexicons, depth
            )
            nodes.append(node)
            continue

        if character == "[":
            flush()
            node, position = _parse_optional(
                text, position, template_id, known_labels, known_identifiers, known_lexicons, depth
            )
            nodes.append(node)
            continue

        if character == "}":
            raise TemplateError(
                template_id, position, "unbalanced-brace", "a closing brace with no opening slot"
            )

        buffer.append(character)
        position += 1

    flush()
    return tuple(nodes), position


def _parse_slot(
    text: str,
    start: int,
    template_id: str,
    known_labels: frozenset[str],
    known_identifiers: frozenset[str],
    known_lexicons: frozenset[str],
) -> tuple[Node, int]:
    close = text.find("}", start)
    if close == -1:
        raise TemplateError(template_id, start, "unbalanced-brace", "slot is never closed")

    body = text[start + 1 : close]
    kind, separator, argument = body.partition(":")
    if not separator:
        raise TemplateError(
            template_id,
            start,
            "malformed-slot",
            f"{{{body}}} has no kind separator; expected one of "
            + ", ".join(f"{{{k}:...}}" for k in sorted(_SLOT_KINDS)),
        )

    kind, argument = kind.strip(), argument.strip()
    if kind not in _SLOT_KINDS:
        raise TemplateError(
            template_id,
            start,
            "unknown-slot-kind",
            f"{kind!r} is not a slot kind; allowed: " + ", ".join(sorted(_SLOT_KINDS)),
        )
    if not argument:
        raise TemplateError(template_id, start, "empty-slot-argument", f"{{{kind}:}} names nothing")

    if kind == "field":
        return FieldSlot(path=argument), close + 1
    if kind == "entity":
        if argument not in known_labels:
            raise TemplateError(
                template_id,
                start,
                "unknown-label",
                f"{argument!r} is outside the closed taxonomy; allowed: "
                + ", ".join(sorted(known_labels)),
            )
        return EntitySlot(label=argument), close + 1
    if kind == "lex":
        if known_lexicons and argument not in known_lexicons:
            raise TemplateError(
                template_id,
                start,
                "unknown-lexicon",
                f"{argument!r} is not a lexicon this pack or the core declares; allowed: "
                + ", ".join(sorted(known_lexicons)),
            )
        return LexiconSlot(name=argument), close + 1

    if argument not in known_identifiers:
        raise TemplateError(
            template_id,
            start,
            "unknown-identifier",
            f"{argument!r} is not an identifier engine; allowed: "
            + ", ".join(sorted(known_identifiers)),
        )
    return IdentifierSlot(identifier=argument), close + 1


def _parse_alternation(
    text: str,
    start: int,
    template_id: str,
    known_labels: frozenset[str],
    known_identifiers: frozenset[str],
    known_lexicons: frozenset[str],
    depth: int,
) -> tuple[Node, int]:
    branches: list[tuple[Node, ...]] = []
    position = start + 1
    while True:
        nodes, position = _parse_sequence(
            text,
            position,
            template_id=template_id,
            known_labels=known_labels,
            known_identifiers=known_identifiers,
            known_lexicons=known_lexicons,
            terminators="|)",
            depth=depth + 1,
        )
        branches.append(nodes)
        if position >= len(text):
            raise TemplateError(
                template_id, start, "unbalanced-paren", "alternation is never closed"
            )
        if text[position] == ")":
            position += 1
            break
        position += 1  # skip the separator

    if len(branches) < 2:
        raise TemplateError(
            template_id,
            start,
            "single-branch-alternation",
            "an alternation with one branch chooses nothing; remove the parentheses",
        )
    return Alternation(branches=tuple(branches)), position


def _parse_optional(
    text: str,
    start: int,
    template_id: str,
    known_labels: frozenset[str],
    known_identifiers: frozenset[str],
    known_lexicons: frozenset[str],
    depth: int,
) -> tuple[Node, int]:
    if not text.startswith("[?", start):
        raise TemplateError(
            template_id, start, "malformed-optional", "an optional segment starts with [?"
        )
    colon = text.find(":", start)
    if colon == -1:
        raise TemplateError(
            template_id, start, "malformed-optional", "[?rate: text] needs a colon after the rate"
        )

    rate = text[start + 2 : colon].strip()
    _validate_rate(template_id, start, rate)

    body, position = _parse_sequence(
        text,
        colon + 1,
        template_id=template_id,
        known_labels=known_labels,
        known_identifiers=known_identifiers,
        known_lexicons=known_lexicons,
        terminators="]",
        depth=depth + 1,
    )
    if position >= len(text) or text[position] != "]":
        raise TemplateError(
            template_id, start, "unbalanced-bracket", "optional segment is never closed"
        )
    return Optional(rate=rate, body=body), position + 1


def _validate_rate(template_id: str, position: int, rate: str) -> None:
    if rate == SPECIAL_RATE:
        return
    try:
        value = Decimal(rate)
    except InvalidOperation:
        raise TemplateError(
            template_id, position, "malformed-probability", f"{rate!r} is not a decimal"
        ) from None
    if not value.is_finite() or not Decimal(0) <= value <= Decimal(1):
        raise TemplateError(
            template_id, position, "probability-out-of-range", f"{rate!r} is not in [0, 1]"
        )
    exponent = value.as_tuple().exponent
    places = max(0, -exponent) if isinstance(exponent, int) else MAX_PROBABILITY_DECIMAL_PLACES + 1
    if places > MAX_PROBABILITY_DECIMAL_PLACES:
        raise TemplateError(
            template_id,
            position,
            "probability-precision-limit",
            f"{rate!r} has {places} decimal places; at most "
            f"{MAX_PROBABILITY_DECIMAL_PLACES} are supported",
        )


def choose_branch(stream: SplitMix64, node: Alternation) -> tuple[Node, ...]:
    """Uniform choice among an alternation's branches."""
    return node.branches[bounded(stream, len(node.branches))]


def include_optional(stream: SplitMix64, node: Optional, special_rate: str = "0") -> bool:
    """Whether an optional segment is included on this draw."""
    return boolean(stream, special_rate if node.defers_to_recipe else node.rate)
