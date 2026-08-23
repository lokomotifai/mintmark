"""RFC 4180 CSV, with the same field order as the JSONL form.

CSV exists because a consumer's pipeline may not read JSONL. It carries the same
records in the same order, so a dataset minted twice in two formats holds the
same data and the manifest can describe both without qualification.

Nested values have no CSV representation. Rather than inventing one, a record
containing a nested value is refused: a silent JSON-inside-a-cell convention
would be a second serialization format that nobody documented.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any


class SpreadsheetFormulaError(ValueError):
    """A string cell would be interpreted as active content by spreadsheets."""


def csv_header(field_order: tuple[str, ...]) -> str:
    """The header row, in declaration order, RFC 4180 quoted, LF terminated."""
    return _render_row(list(field_order))


def render_csv_row(record: dict[str, Any], field_order: tuple[str, ...]) -> str:
    """One record as an RFC 4180 row, LF terminated."""
    missing = [name for name in field_order if name not in record]
    if missing:
        raise ValueError(f"record is missing declared fields: {missing}")

    cells: list[str] = []
    for name in field_order:
        value = record[name]
        if isinstance(value, float):
            raise TypeError(
                f"field {name!r} carries a float; monetary values are integer kurus "
                "and rates are decimal strings"
            )
        if isinstance(value, (dict, list, tuple)):
            raise TypeError(
                f"field {name!r} carries a {type(value).__name__}, which has no CSV "
                "representation. Emit this record type as JSONL, or flatten the field."
            )
        if isinstance(value, str) and _formula_prefix(value) is not None:
            raise SpreadsheetFormulaError(
                f"field {name!r} begins with spreadsheet formula trigger "
                f"{_formula_prefix(value)!r}; CSV emission refuses active cells"
            )
        cells.append("" if value is None else str(value))
    return _render_row(cells)


def _formula_prefix(value: str) -> str | None:
    position = 0
    while position < len(value) and (value[position].isspace() or ord(value[position]) < 0x20):
        position += 1
    candidate = value[position:]
    if re.fullmatch(r"[+-]\d+(?:\.\d+)?", candidate) or re.fullmatch(
        r"\+90 5\d{2} \d{3} \d{2} \d{2}", candidate
    ):
        return None
    if candidate.startswith(("=", "+", "-", "@")):
        return candidate[0]
    return None


def _render_row(cells: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(cells)
    return buffer.getvalue()
