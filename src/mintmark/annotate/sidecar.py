"""Label sidecar files: one JSON object per document.

    {"doc_id": "...", "text_sha256": "...",
     "spans": [{"start": 0, "end": 10, "label": "PERSON"}]}

`text_sha256` binds the spans to the exact text they index. Without it a sidecar
is a set of numbers that look plausible against any document of roughly the right
length, and a consumer who regenerated the data with a different pack version
would get silently wrong offsets rather than an error.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from itertools import pairwise
from typing import TextIO

from mintmark.annotate.spans import Span


def text_digest(text: str) -> str:
    """SHA-256 of the UTF-8 encoding of the document text, lowercase hex."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SidecarRecord:
    """One document's labels."""

    doc_id: str
    text: str
    spans: tuple[Span, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "doc_id": self.doc_id,
            "text_sha256": text_digest(self.text),
            "spans": [span.to_json() for span in self.spans],
        }

    def render(self) -> str:
        """One canonical JSONL line, without its terminator."""
        return json.dumps(self.to_json(), ensure_ascii=False, separators=(",", ":"))


def write_sidecar(handle: TextIO, records: list[SidecarRecord]) -> None:
    """Write records as canonical JSONL: UTF-8, LF, trailing newline."""
    for record in records:
        handle.write(record.render())
        handle.write("\n")


def verify_alignment(record: SidecarRecord) -> list[str]:
    """Return a list of problems, empty when the record is sound.

    Returns rather than raises so that a verifier can report every fault in a
    dataset instead of stopping at the first one.
    """
    problems: list[str] = []
    length = len(record.text)

    for span in record.spans:
        if span.end > length:
            problems.append(
                f"{record.doc_id}: span [{span.start}, {span.end}) for "
                f"{span.label.value} runs past the end of a {length} character document"
            )
            continue
        if not span.extract(record.text).strip():
            problems.append(
                f"{record.doc_id}: span [{span.start}, {span.end}) for "
                f"{span.label.value} covers only whitespace"
            )

    ordered = sorted(record.spans)
    for earlier, later in pairwise(ordered):
        if later.start < earlier.end:
            problems.append(
                f"{record.doc_id}: spans [{earlier.start}, {earlier.end}) and "
                f"[{later.start}, {later.end}) overlap"
            )

    return problems
