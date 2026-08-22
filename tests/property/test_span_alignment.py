"""Invariant 5: every span re-extracts exactly the surface it was recorded for.

Alignment is the property that makes a labeled dataset worth anything. A detector
evaluated against misaligned spans is scored against noise, and the failure is
quiet: the offsets look reasonable, the counts look reasonable, and only the
resulting metric is wrong.

The hard case is whitespace normalization, which happens after slot expansion and
moves every character following a collapsed run. These tests push text through
that transform deliberately.
"""

from __future__ import annotations

from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mintmark.annotate import (
    Label,
    SidecarRecord,
    Span,
    SpanRecorder,
    normalize_whitespace,
    text_digest,
    verify_alignment,
)

QUICK = settings(max_examples=400, deadline=None)

# Filler that mixes ordinary text with the whitespace runs that move offsets.
filler = st.text(alphabet=" \t\n abcçğıöşü.,;", min_size=0, max_size=30)
surface = st.text(alphabet="abcçğıöşüABCÇĞİÖŞÜ0123456789", min_size=1, max_size=20)
labels = st.sampled_from(list(Label))


def test_a_span_after_a_collapsed_run_still_extracts() -> None:
    """The concrete case the index map exists for."""
    recorder = SpanRecorder()
    recorder.append("Sayin      ")
    recorder.append_labeled("Ayşe Yılmaz", Label.PERSON)
    recorder.append(",\n\n   hesabiniz   ")
    recorder.append_labeled("TR990000000000000000000000", Label.IBAN)
    recorder.append(" numarali.")

    text, spans = recorder.finalize()
    assert "  " not in text, "normalization did not collapse the runs"
    for span in spans:
        assert span.extract(text)
    assert spans[0].extract(text) == "Ayşe Yılmaz"
    assert spans[1].extract(text) == "TR990000000000000000000000"


@QUICK
@given(
    prefix=filler,
    body=surface,
    middle=filler,
    second=surface,
    suffix=filler,
    label_a=labels,
    label_b=labels,
)
def test_every_span_re_extracts_over_arbitrary_whitespace(
    prefix: str,
    body: str,
    middle: str,
    second: str,
    suffix: str,
    label_a: Label,
    label_b: Label,
) -> None:
    recorder = SpanRecorder()
    recorder.append(prefix)
    recorder.append_labeled(body, label_a)
    recorder.append(middle)
    recorder.append_labeled(second, label_b)
    recorder.append(suffix)

    text, spans = recorder.finalize()
    assert len(spans) == 2
    # Spans come back sorted by position, and the two labeled pieces were
    # appended in order, so the pairing is unambiguous even when both carry the
    # same label.
    assert spans[0].extract(text) == body
    assert spans[1].extract(text) == second
    assert spans[0].label is label_a
    assert spans[1].label is label_b


@QUICK
@given(raw=st.text(alphabet=" \t\n\rabc", min_size=0, max_size=60))
def test_normalization_leaves_no_double_space_and_no_edge_space(raw: str) -> None:
    text, _ = normalize_whitespace(raw)
    assert "  " not in text
    assert text == text.strip()


@QUICK
@given(raw=st.text(alphabet=" \t\nabc", min_size=0, max_size=60))
def test_index_map_covers_every_position_plus_one(raw: str) -> None:
    text, index_map = normalize_whitespace(raw)
    assert len(index_map) == len(raw) + 1
    assert index_map[-1] == len(text)
    assert all(0 <= position <= len(text) for position in index_map)
    assert all(a <= b for a, b in pairwise(index_map))


def test_labeling_an_empty_surface_is_refused() -> None:
    recorder = SpanRecorder()
    with pytest.raises(ValueError, match="cannot label an empty surface"):
        recorder.append_labeled("", Label.PERSON)


def test_a_whitespace_only_surface_is_refused_at_finalize() -> None:
    """It would collapse to nothing, leaving a span pointing at no text."""
    recorder = SpanRecorder()
    recorder.append("before ")
    recorder.append_labeled("   ", Label.PERSON)
    recorder.append(" after")
    with pytest.raises(ValueError, match="vanished under whitespace normalization"):
        recorder.finalize()


def test_spans_come_back_sorted_by_position() -> None:
    recorder = SpanRecorder()
    recorder.append_labeled("first", Label.PERSON)
    recorder.append(" middle ")
    recorder.append_labeled("second", Label.ORG)
    _, spans = recorder.finalize()
    assert spans == sorted(spans)
    assert spans[0].start < spans[1].start


def test_turkish_characters_do_not_shift_offsets() -> None:
    """Offsets are code points, so a multi-byte character is still one position."""
    recorder = SpanRecorder()
    recorder.append("Şşğüöçİı ")
    recorder.append_labeled("Ağrı", Label.ADDRESS)
    text, spans = recorder.finalize()
    assert spans[0].extract(text) == "Ağrı"
    assert spans[0].start == 9


@pytest.mark.parametrize(("start", "end"), [(-1, 5), (5, 5), (6, 5)])
def test_malformed_span_bounds_are_refused(start: int, end: int) -> None:
    with pytest.raises(ValueError, match=r"non-negative|non-empty"):
        Span(start=start, end=end, label=Label.PERSON)


def test_sidecar_binds_spans_to_the_exact_text() -> None:
    record = SidecarRecord(
        doc_id="CMP-00000001",
        text="Ayşe Yılmaz aradi.",
        spans=(Span(0, 11, Label.PERSON),),
    )
    payload = record.to_json()
    assert payload["text_sha256"] == text_digest("Ayşe Yılmaz aradi.")
    assert payload["spans"] == [{"start": 0, "end": 11, "label": "PERSON"}]
    assert not verify_alignment(record)


def test_sidecar_carries_a_digest_rather_than_the_document_text() -> None:
    """The sidecar binds spans to text without duplicating it.

    Duplicating the text would double the size of every labeled dataset and
    would create a second copy that could drift from the first.
    """
    record = SidecarRecord("D1", "Çiğdem Şahin", (Span(0, 6, Label.PERSON),))
    line = record.render()
    assert "Çiğdem" not in line
    assert text_digest("Çiğdem Şahin") in line
    assert line.isascii(), "the sidecar line carries only ids, digests, and offsets"


def test_verify_alignment_reports_a_span_past_the_end() -> None:
    record = SidecarRecord("D1", "short", (Span(0, 99, Label.PERSON),))
    problems = verify_alignment(record)
    assert problems
    assert "runs past the end" in problems[0]


def test_verify_alignment_reports_overlapping_spans() -> None:
    record = SidecarRecord("D1", "abcdefghij", (Span(0, 6, Label.PERSON), Span(4, 9, Label.ORG)))
    problems = verify_alignment(record)
    assert problems
    assert "overlap" in problems[0]


def test_verify_alignment_reports_every_fault_not_only_the_first() -> None:
    """A verifier should describe a dataset, not stop at its first surprise."""
    record = SidecarRecord("D1", "abcde", (Span(0, 99, Label.PERSON), Span(1, 100, Label.ORG)))
    assert len(verify_alignment(record)) >= 2
