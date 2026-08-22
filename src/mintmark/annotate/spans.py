"""Span recording that survives whitespace normalization.

Rendering a document is two passes. The first expands template slots and records
where each labeled surface landed. The second normalizes whitespace, which moves
every character after each collapsed run.

Recording offsets in the first pass and using them in the second would misalign
every span that followed a collapsed run of spaces, and the misalignment would be
small enough to look like an off-by-one rather than a structural bug. So the
normalizer builds an index map as it goes, and spans are translated through it.

Offsets are 0-based Unicode code points, end-exclusive, over the final text.
Python indexes strings by code point, so an offset recorded here is directly
usable by a consumer reading the same text.
"""

from __future__ import annotations

from dataclasses import dataclass

from mintmark.annotate.taxonomy import Label

# Punctuation that binds to the word before it in Turkish and English.
CLINGING_PUNCTUATION = frozenset(",.;:!?)]}%")


@dataclass(frozen=True, slots=True, order=True)
class Span:
    """One labeled surface in a document."""

    start: int
    end: int
    label: Label

    def __post_init__(self) -> None:
        if self.start < 0:
            raise ValueError(f"span start must be non-negative, got {self.start}")
        if self.end <= self.start:
            raise ValueError(f"span must be non-empty, got [{self.start}, {self.end})")

    def extract(self, text: str) -> str:
        return text[self.start : self.end]

    def to_json(self) -> dict[str, int | str]:
        return {"start": self.start, "end": self.end, "label": self.label.value}


def normalize_whitespace(raw: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to single spaces and return an index map.

    The map has one entry per raw index plus a final entry, so that both ends of
    a half-open span can be translated. A raw index inside a collapsed run maps
    to the position of the single space that replaced it.
    """
    out: list[str] = []
    index_map: list[int] = []
    previous_was_space = True  # leading whitespace is dropped entirely

    for character in raw:
        index_map.append(len(out))
        if character.isspace():
            if not previous_was_space:
                out.append(" ")
                previous_was_space = True
            continue
        # A space immediately before sentence punctuation is dropped. Template
        # optionals naturally begin with the separator they introduce, as in
        # "[?0.3:, ayrica ...]", and without this rule every such segment would
        # render as "gerceklesti , ayrica". Any span this disturbs is caught by
        # the re-extraction check in finalize rather than shipped misaligned.
        if character in CLINGING_PUNCTUATION and out and out[-1] == " ":
            out.pop()
        out.append(character)
        previous_was_space = False

    # Trailing whitespace collapsed to a single space is dropped.
    while out and out[-1] == " ":
        out.pop()

    index_map.append(len(out))
    normalized = "".join(out)

    # An index that pointed past the trimmed tail clamps to the end of the text.
    limit = len(normalized)
    return normalized, [min(position, limit) for position in index_map]


class SpanRecorder:
    """Accumulates raw text and the labeled surfaces placed into it.

    A renderer appends every piece of the document through this recorder, marking
    the pieces that carry a label. `finalize` normalizes the accumulated text and
    returns spans translated into the normalized coordinate system.
    """

    __slots__ = ("_length", "_pending", "_pieces")

    def __init__(self) -> None:
        self._pieces: list[str] = []
        self._pending: list[tuple[int, int, Label]] = []
        self._length = 0

    def append(self, text: str) -> None:
        """Append unlabeled text."""
        self._pieces.append(text)
        self._length += len(text)

    def append_labeled(self, text: str, label: Label) -> None:
        """Append text and record it as a labeled span."""
        if not text:
            raise ValueError(f"cannot label an empty surface as {label.value}")
        start = self._length
        self._pieces.append(text)
        self._length += len(text)
        self._pending.append((start, self._length, label))

    @property
    def raw(self) -> str:
        return "".join(self._pieces)

    def finalize(self) -> tuple[str, list[Span]]:
        """Return the normalized text and its spans, verified against that text.

        Every span is re-extracted and compared to the surface it was recorded
        for before being returned. A recorder that produced a misaligned span
        raises here rather than writing a sidecar that a consumer would trust.
        """
        raw = self.raw
        normalized, index_map = normalize_whitespace(raw)

        spans: list[Span] = []
        for raw_start, raw_end, label in self._pending:
            start = index_map[raw_start]
            end = index_map[raw_end]
            if end <= start:
                # The surface collapsed entirely, which means it was whitespace.
                raise ValueError(
                    f"labeled surface {raw[raw_start:raw_end]!r} for {label.value} "
                    "vanished under whitespace normalization"
                )

            expected = " ".join(raw[raw_start:raw_end].split())
            actual = normalized[start:end]
            if actual != expected:
                raise ValueError(
                    f"span misalignment for {label.value}: recorded {expected!r} "
                    f"but the text at [{start}, {end}) reads {actual!r}"
                )
            spans.append(Span(start=start, end=end, label=label))

        spans.sort()
        return normalized, spans
