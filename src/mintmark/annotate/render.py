"""Rendering a parsed template into text plus its label spans.

This is the layer where `engine` and `annotate` meet. The template grammar is
structural and lives in `engine`, which imports only the standard library; the
taxonomy and span recording live here. Rendering needs both, so it lives on the
`annotate` side of the boundary and takes its resolvers as callbacks.

Every slot that carries a label records its span while it is placed, not
afterwards by searching the finished text for the value. Searching would find the
wrong occurrence whenever a value appears twice, which in a document naming the
same person in two sentences is not an edge case.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from mintmark.annotate.spans import Span, SpanRecorder
from mintmark.annotate.taxonomy import Label, parse_label
from mintmark.engine.prng import SplitMix64
from mintmark.engine.templates import (
    Alternation,
    EntitySlot,
    FieldSlot,
    IdentifierSlot,
    Literal,
    Node,
    Optional,
    choose_branch,
    include_optional,
)


class RenderError(ValueError):
    """A slot could not be resolved against the record graph at render time."""


@dataclass(frozen=True, slots=True)
class Resolvers:
    """How a render resolves each slot kind.

    Passed in rather than imported so that this module depends on no particular
    pack, lexicon, or identifier policy. The mint assembles them once.

    Each resolver returns the surface text. Whether that surface carries a label
    is decided here, from the slot kind and the taxonomy, not by the resolver.
    """

    field: Callable[[str], object]
    entity: Callable[[Label, SplitMix64], str]
    identifier: Callable[[str, SplitMix64], str]
    field_label: Callable[[str], Label | None]


def render(
    nodes: tuple[Node, ...],
    *,
    stream: SplitMix64,
    resolvers: Resolvers,
) -> tuple[str, list[Span]]:
    """Render nodes into normalized text and its spans."""
    recorder = SpanRecorder()
    _emit(nodes, stream=stream, resolvers=resolvers, recorder=recorder)
    return recorder.finalize()


def _emit(
    nodes: tuple[Node, ...],
    *,
    stream: SplitMix64,
    resolvers: Resolvers,
    recorder: SpanRecorder,
) -> None:
    for node in nodes:
        match node:
            case Literal(text=text):
                recorder.append(text)

            case FieldSlot(path=path):
                value = resolvers.field(path)
                if value is None:
                    # A null field renders as nothing rather than as the word
                    # "None". A template that needs the difference wraps the slot
                    # in an optional segment.
                    continue
                surface = str(value)
                if not surface:
                    continue
                label = resolvers.field_label(path)
                if label is None:
                    recorder.append(surface)
                else:
                    recorder.append_labeled(surface, label)

            case EntitySlot(label=label_name):
                label = parse_label(label_name)
                surface = resolvers.entity(label, stream)
                if not surface:
                    raise RenderError(f"the lexicon for {label_name} produced an empty surface")
                recorder.append_labeled(surface, label)

            case IdentifierSlot(identifier=identifier):
                surface = resolvers.identifier(identifier, stream)
                recorder.append_labeled(surface, parse_label(identifier))

            case Alternation():
                _emit(
                    choose_branch(stream, node),
                    stream=stream,
                    resolvers=resolvers,
                    recorder=recorder,
                )

            case Optional():
                if include_optional(stream, node):
                    _emit(node.body, stream=stream, resolvers=resolvers, recorder=recorder)
