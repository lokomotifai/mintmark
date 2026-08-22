"""Taxonomy, span capture, and sidecar writing.

`import-linter` holds this package to importing only `engine`.
"""

from __future__ import annotations

from mintmark.annotate.render import RenderError, Resolvers, render
from mintmark.annotate.sidecar import (
    SidecarRecord,
    text_digest,
    verify_alignment,
    write_sidecar,
)
from mintmark.annotate.spans import Span, SpanRecorder, normalize_whitespace
from mintmark.annotate.taxonomy import (
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

__all__ = [
    "ALL_LABELS",
    "DETERMINISTIC_LABELS",
    "NER_LABELS",
    "SPECIAL_CATEGORY_LABELS",
    "TAXONOMY_NAME",
    "TAXONOMY_VERSION",
    "Label",
    "RenderError",
    "Resolvers",
    "SidecarRecord",
    "Span",
    "SpanRecorder",
    "UnknownLabelError",
    "normalize_whitespace",
    "parse_label",
    "pin",
    "pin_digest",
    "render",
    "text_digest",
    "verify_alignment",
    "write_sidecar",
]
