"""Verification: recompute everything, trust nothing that was recorded.

`verify` re-derives every claim the manifest makes rather than reading a flag
that says the claim held. Checksums are recomputed from the files on disk, spans
are re-extracted from the text they index, and under a safe policy every
identifier is put through the same validator a consumer would apply.

The identifier validators are injected rather than imported, because `manifest`
sits above `identifiers` in the declared dependency direction. The composition
happens in the CLI, which is the layer that knows about both.

Problems are collected rather than raised. A verifier that stops at the first
fault describes one symptom; a consumer deciding whether to trust a dataset wants
the whole picture.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from itertools import islice, pairwise
from pathlib import Path
from typing import Any

import jsonschema

from mintmark.manifest.document import MANIFEST_FILENAME, VALIDATOR_WARNING, read_manifest
from mintmark.manifest.io import (
    MAX_CONTROL_FILE_BYTES,
    MAX_DATA_FILE_BYTES,
    DatasetIOError,
    DatasetReader,
)
from mintmark.manifest.safety import identifier_candidates
from mintmark.manifest.sums import SUMS_FILENAME, parse_sums

Validator = Callable[[str], bool]
MAX_SCHEMA_PROBLEMS = 100


@dataclass(slots=True)
class VerifyReport:
    """Everything verification observed, sound or not."""

    directory: str
    schema_valid: bool = False
    checksums_checked: int = 0
    checksums_matched: int = 0
    identifier_policy: str = "unknown"
    checksum_valid_identifiers: int = 0
    documents_checked: int = 0
    spans_checked: int = 0
    taxonomy_pin: str = ""
    dataset_license: str = "unknown"
    attribution: str = ""
    problems: list[str] = dataclass_field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def to_json(self) -> dict[str, Any]:
        return {
            "directory": self.directory,
            "ok": self.ok,
            "schema_valid": self.schema_valid,
            "checksums": {"checked": self.checksums_checked, "matched": self.checksums_matched},
            "identifier_policy": self.identifier_policy,
            "checksum_valid_identifiers": self.checksum_valid_identifiers,
            "documents_checked": self.documents_checked,
            "spans_checked": self.spans_checked,
            "taxonomy_pin": self.taxonomy_pin,
            "dataset_license": self.dataset_license,
            "attribution": self.attribution,
            "problems": list(self.problems),
        }

    def render(self) -> str:
        lines = [
            f"manifest schema: {'valid' if self.schema_valid else 'INVALID'}",
            f"checksums: {self.checksums_matched}/{self.checksums_checked} match",
            f"identifier policy: {self.identifier_policy} (confirmed)"
            if self.identifier_policy != "unknown"
            else "identifier policy: unknown",
            f"checksum-valid identifiers found: {self.checksum_valid_identifiers}",
            f"taxonomy: {self.taxonomy_pin}",
            f"label alignment: {self.documents_checked} documents, {self.spans_checked} spans",
            f"dataset license: {self.dataset_license}",
            f"attribution: {self.attribution}",
        ]
        lines.extend(f"PROBLEM: {problem}" for problem in self.problems)
        return "\n".join(lines)


def verify(
    directory: Path,
    *,
    schema: dict[str, Any],
    validators: dict[str, Validator],
    expected_taxonomy_pin: str | None = None,
    known_labels: frozenset[str] = frozenset(),
) -> VerifyReport:
    """Recompute every claim the manifest makes."""
    directory = Path(directory)
    report = VerifyReport(directory=str(directory))

    try:
        reader = DatasetReader(directory)
    except (DatasetIOError, OSError, ValueError) as exc:
        report.problems.append(str(exc))
        return report

    with reader:
        try:
            document = read_manifest(directory, reader=reader)
        except (OSError, ValueError) as exc:
            report.problems.append(str(exc))
            return report

        try:
            errors = list(
                islice(
                    jsonschema.Draft202012Validator(schema).iter_errors(document),
                    MAX_SCHEMA_PROBLEMS + 1,
                )
            )
        except (RecursionError, TypeError, ValueError) as exc:
            report.problems.append(f"{MANIFEST_FILENAME}: schema validation failed safely: {exc}")
            return report
        report.schema_valid = not errors
        for error in errors[:MAX_SCHEMA_PROBLEMS]:
            location = "/".join(str(part) for part in error.absolute_path) or "document"
            report.problems.append(f"{MANIFEST_FILENAME}: {location}: {error.message}")
        if len(errors) > MAX_SCHEMA_PROBLEMS:
            report.problems.append(
                f"{MANIFEST_FILENAME}: more than {MAX_SCHEMA_PROBLEMS} schema problems; "
                "remaining errors omitted"
            )
        if errors:
            return report

        report.identifier_policy = document["identifier_policy"]
        # Reported rather than merely stored. Somebody running verify on a dataset
        # they downloaded is exactly the person who needs to know the terms, and the
        # credit line they would otherwise have to assemble by hand.
        report.dataset_license = document["license"]["datasets"]
        report.attribution = document["license"]["attribution"]
        taxonomy = document["taxonomy"]
        report.taxonomy_pin = (
            f"{taxonomy['name']} v{taxonomy['version']}, pin {taxonomy['pin_digest'][:12]}"
        )

        if expected_taxonomy_pin is not None and taxonomy["pin_digest"] != expected_taxonomy_pin:
            report.problems.append(
                f"taxonomy pin {taxonomy['pin_digest']} does not match this engine's "
                f"{expected_taxonomy_pin}; the dataset was minted against a different label set"
            )

        if not _check_manifest_semantics(document, report):
            return report
        _check_validator_warning(document, report)
        _check_checksums(reader, document, report)
        _check_sums_file(reader, document, report)
        _check_spans(reader, document, report, known_labels=known_labels)
        if report.identifier_policy == "safe":
            _sweep_identifiers(reader, document, validators, report)

    return report


def _check_manifest_semantics(document: dict[str, Any], report: VerifyReport) -> bool:
    """Enforce cross-field constraints JSON Schema cannot express."""
    paths = [output["path"] for output in document["outputs"]]
    duplicates = sorted({path for path in paths if paths.count(path) > 1})
    for path in duplicates:
        report.problems.append(f"{MANIFEST_FILENAME}: duplicate output path {path!r}")
    for reserved in (MANIFEST_FILENAME, SUMS_FILENAME):
        if reserved in paths:
            report.problems.append(f"{MANIFEST_FILENAME}: outputs may not claim {reserved}")
    try:
        seed = int(document["seed"])
    except ValueError:
        report.problems.append(f"{MANIFEST_FILENAME}: seed is not an integer")
    else:
        if not 0 <= seed < 1 << 64:
            report.problems.append(f"{MANIFEST_FILENAME}: seed is outside the u64 range")
    return not report.problems


def _check_validator_warning(document: dict[str, Any], report: VerifyReport) -> None:
    """A validator dataset without its warning is the failure this catches.

    Stripping the warning is how a checksum-valid dataset would end up circulating
    without the one sentence that says what it is.
    """
    present = "validator_warning" in document
    if document["identifier_policy"] == "validator":
        if not present:
            report.problems.append(
                "policy is validator but the manifest carries no validator_warning"
            )
        elif document["validator_warning"] != VALIDATOR_WARNING:
            report.problems.append("validator_warning has been altered from the fixed text")
    elif present:
        report.problems.append("validator_warning present under a safe policy")


def _check_checksums(
    reader: DatasetReader, document: dict[str, Any], report: VerifyReport
) -> None:
    for output in document["outputs"]:
        report.checksums_checked += 1
        try:
            actual, size = reader.digest(output["path"], max_bytes=MAX_DATA_FILE_BYTES)
        except (DatasetIOError, OSError) as exc:
            report.problems.append(str(exc))
            continue
        if actual != output["sha256"]:
            report.problems.append(
                f"{output['path']}: checksum mismatch\n"
                f"  recorded {output['sha256']}\n  actual   {actual}"
            )
            continue
        if size != output["bytes"]:
            report.problems.append(
                f"{output['path']}: size {size} does not match the recorded {output['bytes']}"
            )
            continue
        report.checksums_matched += 1

    listed = {output["path"] for output in document["outputs"]} | {
        MANIFEST_FILENAME,
        SUMS_FILENAME,
    }
    try:
        entries = reader.entries()
    except (DatasetIOError, OSError) as exc:
        report.problems.append(str(exc))
        return
    for entry in entries:
        if entry.kind != "file":
            report.problems.append(f"{entry.name}: unsafe dataset entry type: {entry.kind}")
        if entry.name not in listed:
            report.problems.append(
                f"{entry.name}: present in the directory but absent from the manifest"
            )


def _check_sums_file(
    reader: DatasetReader, document: dict[str, Any], report: VerifyReport
) -> None:
    try:
        recorded = parse_sums(
            reader.read_text(SUMS_FILENAME, max_bytes=MAX_CONTROL_FILE_BYTES)
        )
    except (DatasetIOError, OSError, ValueError) as exc:
        report.problems.append(str(exc))
        return
    for output in document["outputs"]:
        if recorded.get(output["path"]) != output["sha256"]:
            report.problems.append(f"{output['path']}: {SUMS_FILENAME} disagrees with the manifest")

    # The manifest lists every output but never itself, so its own line in
    # SHA256SUMS has nothing in the manifest to compare against. Left unchecked,
    # that one line could be altered freely while everything else verified. It is
    # checked against the manifest file on disk instead.
    if MANIFEST_FILENAME not in recorded:
        report.problems.append(f"{SUMS_FILENAME} does not cover {MANIFEST_FILENAME}")
    else:
        try:
            manifest_digest, _ = reader.digest(
                MANIFEST_FILENAME, max_bytes=MAX_CONTROL_FILE_BYTES
            )
        except (DatasetIOError, OSError) as exc:
            report.problems.append(str(exc))
        else:
            if recorded[MANIFEST_FILENAME] != manifest_digest:
                report.problems.append(
                    f"{MANIFEST_FILENAME}: {SUMS_FILENAME} records a digest that does not "
                    "match the manifest on disk"
                )

    expected = {output["path"] for output in document["outputs"]} | {MANIFEST_FILENAME}
    for extra in sorted(set(recorded) - expected):
        report.problems.append(f"{SUMS_FILENAME} lists {extra!r}, which the manifest does not")
    for missing in sorted(expected - set(recorded)):
        report.problems.append(f"{SUMS_FILENAME} omits {missing!r}")


def _check_spans(
    reader: DatasetReader,
    document: dict[str, Any],
    report: VerifyReport,
    *,
    known_labels: frozenset[str],
) -> None:
    """Re-extract every span from the text it indexes."""
    import hashlib

    names = {output["path"] for output in document["outputs"]}
    for sidecar_name in sorted(name for name in names if name.endswith(".labels.jsonl")):
        stem = sidecar_name.removesuffix(".labels.jsonl")
        data_name = _find_data_file(names, stem)
        if data_name is None:
            report.problems.append(f"{sidecar_name}: no data file named {stem}")
            continue

        try:
            texts = _document_texts(reader, data_name)
            sidecar_text = reader.read_text(sidecar_name, max_bytes=MAX_DATA_FILE_BYTES)
        except (DatasetIOError, OSError, ValueError) as exc:
            report.problems.append(str(exc))
            continue
        sidecar_ids: set[str] = set()
        for number, line in enumerate(sidecar_text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, RecursionError):
                report.problems.append(f"{sidecar_name} line {number}: not valid JSON")
                continue
            report.documents_checked += 1
            if not isinstance(record, dict) or not isinstance(record.get("doc_id"), str):
                report.problems.append(f"{sidecar_name} line {number}: malformed sidecar record")
                continue
            text = texts.get(record["doc_id"])
            if record["doc_id"] in sidecar_ids:
                report.problems.append(
                    f"{sidecar_name} line {number}: duplicate document {record['doc_id']!r}"
                )
                continue
            sidecar_ids.add(record["doc_id"])
            if text is None:
                report.problems.append(
                    f"{sidecar_name} line {number}: no document {record['doc_id']}"
                )
                continue
            if not isinstance(record.get("text_sha256"), str) or not isinstance(
                record.get("spans"), list
            ):
                report.problems.append(f"{sidecar_name} line {number}: malformed sidecar record")
                continue
            actual_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if actual_digest != record["text_sha256"]:
                report.problems.append(
                    f"{sidecar_name} line {number}: text_sha256 does not match the document"
                )
                continue
            intervals: list[tuple[int, int]] = []
            for span in record["spans"]:
                report.spans_checked += 1
                if (
                    not isinstance(span, dict)
                    or not isinstance(span.get("start"), int)
                    or not isinstance(span.get("end"), int)
                ):
                    report.problems.append(f"{sidecar_name} line {number}: malformed span")
                    continue
                if isinstance(span["start"], bool) or isinstance(span["end"], bool):
                    report.problems.append(f"{sidecar_name} line {number}: malformed span")
                    continue
                label = span.get("label")
                if not isinstance(label, str) or label not in known_labels:
                    report.problems.append(
                        f"{sidecar_name} line {number}: unknown taxonomy label {label!r}"
                    )
                    continue
                if span["end"] > len(text) or span["start"] < 0 or span["start"] >= span["end"]:
                    report.problems.append(
                        f"{sidecar_name} line {number}: span [{span['start']}, {span['end']}) "
                        f"falls outside a {len(text)} character document"
                    )
                elif not text[span["start"] : span["end"]].strip():
                    report.problems.append(
                        f"{sidecar_name} line {number}: span [{span['start']}, "
                        f"{span['end']}) covers only whitespace"
                    )
                intervals.append((span["start"], span["end"]))
            ordered = sorted(intervals)
            if len(set(ordered)) != len(ordered):
                report.problems.append(f"{sidecar_name} line {number}: duplicate spans")
            for earlier, later in pairwise(ordered):
                if later[0] < earlier[1]:
                    report.problems.append(f"{sidecar_name} line {number}: overlapping spans")
        for missing in sorted(set(texts) - sidecar_ids):
            report.problems.append(f"{sidecar_name}: omits document {missing!r}")


def _find_data_file(names: set[str], stem: str) -> str | None:
    for suffix in (".jsonl", ".csv"):
        candidate = f"{stem}{suffix}"
        if candidate in names:
            return candidate
    return None


def _document_texts(reader: DatasetReader, name: str) -> dict[str, str]:
    """Map document id to text, for whichever field carries the document."""
    texts: dict[str, str] = {}
    if not name.endswith(".jsonl"):
        return texts
    for number, line in enumerate(
        reader.read_text(name, max_bytes=MAX_DATA_FILE_BYTES).splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ValueError(f"{name} line {number}: not valid JSON") from exc
        if not isinstance(record, dict):
            continue
        doc_id = next((v for k, v in record.items() if k.endswith("_id")), None)
        if doc_id is None:
            continue
        document_id = str(doc_id)
        if document_id in texts:
            raise ValueError(f"{name} line {number}: duplicate document id {document_id!r}")
        for key, value in record.items():
            if key in {"body", "description", "text", "note"} and isinstance(value, str):
                texts[document_id] = value
                break
    return texts


def _sweep_identifiers(
    reader: DatasetReader,
    document: dict[str, Any],
    validators: dict[str, Validator],
    report: VerifyReport,
) -> None:
    """Invariant 2, checked on the artifacts rather than on the generator.

    Only the string values of data files are examined. Two earlier approaches were
    wrong in ways worth recording.

    Scanning raw file text swept the label sidecars too, and a sidecar carries no
    data at all: only document ids, SHA-256 digests, and offsets. A digest is hex,
    so it regularly contains a ten-digit run, and about one such run in ten passes
    the VKN check by chance. The sweep fired on its own checksum. A safety check
    that cries wolf gets switched off, which is worse than not having it.

    Scanning parsed values but matching unanchored would have the same problem
    inside any long alphanumeric field, so the pattern is anchored on both sides.
    """
    names = sorted(output["path"] for output in document["outputs"])
    for name in (item for item in names if item.endswith(".jsonl")):
        if name.endswith(".labels.jsonl"):
            continue
        try:
            text = reader.read_text(name, max_bytes=MAX_DATA_FILE_BYTES)
        except (DatasetIOError, OSError) as exc:
            report.problems.append(str(exc))
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, RecursionError):
                report.problems.append(f"{name} line {number}: not valid JSON")
                continue
            for candidate in identifier_candidates(record):
                for validator_name, validator in validators.items():
                    if validator(candidate):
                        report.checksum_valid_identifiers += 1
                        report.problems.append(
                            f"{name} line {number}: contains a checksum-valid "
                            f"{validator_name} under a safe policy; safe mode is the "
                            "product's safety claim"
                        )

    for name in (item for item in names if item.endswith(".csv")):
        try:
            text = reader.read_text(name, max_bytes=MAX_DATA_FILE_BYTES)
        except (DatasetIOError, OSError) as exc:
            report.problems.append(str(exc))
            continue
        for candidate in identifier_candidates(text):
            for validator_name, validator in validators.items():
                if validator(candidate):
                    report.checksum_valid_identifiers += 1
                    report.problems.append(
                        f"{name}: contains a checksum-valid {validator_name} "
                        "under a safe policy"
                    )
