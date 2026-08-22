"""Canonical serialization: the exact bytes a mint writes.

JSONL is UTF-8, LF line endings, one record per line, a trailing newline at end
of file, ASCII escaping off so Turkish characters appear literally, and object
keys in the order the record type declares them.

Key order is not cosmetic. `reproduce` compares bytes, so a serializer that
sorted keys or used insertion order would produce a different file from the same
data and report a mismatch that is not one. Declaration order is also what a
consumer's schema expects when reading a CSV of the same records.

No float ever reaches a data file. The encoder raises rather than serializing
one, because a float in emitted data would make the bytes depend on the
platform's formatting of a binary approximation, which is exactly what the
determinism claim rules out.
"""

from __future__ import annotations

import json
from typing import Any


class FloatInOutputError(TypeError):
    """A float reached the emission boundary."""


class CanonicalEncoder(json.JSONEncoder):
    """A JSON encoder that refuses floats instead of formatting them."""

    def __init__(self) -> None:
        super().__init__(
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
            sort_keys=False,
            check_circular=True,
        )

    def default(self, o: Any) -> Any:
        if isinstance(o, float):
            raise FloatInOutputError(
                f"a float ({o!r}) reached emission. Monetary values are integer "
                "kurus in a field suffixed _kurus; rates and ratios are decimal "
                "strings. A float here would make the emitted bytes depend on the "
                "platform's formatting of a binary approximation."
            )
        raise TypeError(f"cannot serialize {type(o).__name__} into a data file")


_ENCODER = CanonicalEncoder()


def _reject_floats(value: Any, path: str = "") -> None:
    """Walk a record and refuse any float, at any depth.

    The encoder's `default` hook is never called for a float, because json
    handles floats natively. Refusing them therefore has to happen on the way in.
    """
    if isinstance(value, float):
        raise FloatInOutputError(
            f"a float ({value!r}) reached emission at {path or 'the record root'}. "
            "Monetary values are integer kurus; rates and ratios are decimal strings."
        )
    if isinstance(value, dict):
        for key, item in value.items():
            _reject_floats(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_floats(item, f"{path}[{index}]")


def render_record(record: dict[str, Any], field_order: tuple[str, ...]) -> str:
    """One canonical JSONL line, without its terminator.

    Fields are written in declaration order. A field the record does not carry is
    an error rather than an omission: a record type that declares a field and a
    record that lacks it disagree, and silently writing a shorter line would push
    that disagreement into the consumer's parser.
    """
    _reject_floats(record)
    missing = [name for name in field_order if name not in record]
    if missing:
        raise ValueError(f"record is missing declared fields: {missing}")
    extra = [name for name in record if name not in field_order]
    if extra:
        raise ValueError(f"record carries undeclared fields: {extra}")
    ordered = {name: record[name] for name in field_order}
    return _ENCODER.encode(ordered)
