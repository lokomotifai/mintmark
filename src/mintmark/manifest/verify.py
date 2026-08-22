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
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any

import jsonschema

from mintmark.manifest.document import MANIFEST_FILENAME, VALIDATOR_WARNING, read_manifest
from mintmark.manifest.sums import SUMS_FILENAME, file_digest, parse_sums

Validator = Callable[[str], bool]


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
        ]
        lines.extend(f"PROBLEM: {problem}" for problem in self.problems)
        return "\n".join(lines)


def verify(
    directory: Path,
    *,
    schema: dict[str, Any],
    validators: dict[str, Validator],
    expected_taxonomy_pin: str | None = None,
) -> VerifyReport:
    """Recompute every claim the manifest makes."""
    directory = Path(directory)
    report = VerifyReport(directory=str(directory))

    document = read_manifest(directory)

    errors = sorted(
        jsonschema.Draft202012Validator(schema).iter_errors(document),
        key=lambda e: list(e.absolute_path),
    )
    report.schema_valid = not errors
    for error in errors:
        location = "/".join(str(part) for part in error.absolute_path) or "document"
        report.problems.append(f"{MANIFEST_FILENAME}: {location}: {error.message}")
    if errors:
        return report

    report.identifier_policy = document["identifier_policy"]
    taxonomy = document["taxonomy"]
    report.taxonomy_pin = (
        f"{taxonomy['name']} v{taxonomy['version']}, pin {taxonomy['pin_digest'][:12]}"
    )

    if expected_taxonomy_pin is not None and taxonomy["pin_digest"] != expected_taxonomy_pin:
        report.problems.append(
            f"taxonomy pin {taxonomy['pin_digest']} does not match this engine's "
            f"{expected_taxonomy_pin}; the dataset was minted against a different label set"
        )

    _check_validator_warning(document, report)
    _check_checksums(directory, document, report)
    _check_sums_file(directory, document, report)
    _check_spans(directory, report)
    if report.identifier_policy == "safe":
        _sweep_identifiers(directory, validators, report)

    return report


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


def _check_checksums(directory: Path, document: dict[str, Any], report: VerifyReport) -> None:
    for output in document["outputs"]:
        path = directory / output["path"]
        report.checksums_checked += 1
        if not path.exists():
            report.problems.append(f"{output['path']}: listed in the manifest but missing")
            continue
        actual = file_digest(path)
        if actual != output["sha256"]:
            report.problems.append(
                f"{output['path']}: checksum mismatch\n"
                f"  recorded {output['sha256']}\n  actual   {actual}"
            )
            continue
        size = path.stat().st_size
        if size != output["bytes"]:
            report.problems.append(
                f"{output['path']}: size {size} does not match the recorded {output['bytes']}"
            )
            continue
        report.checksums_matched += 1

    listed = {output["path"] for output in document["outputs"]}
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        if relative in {MANIFEST_FILENAME, SUMS_FILENAME} or relative in listed:
            continue
        report.problems.append(f"{relative}: present in the directory but absent from the manifest")


def _check_sums_file(directory: Path, document: dict[str, Any], report: VerifyReport) -> None:
    path = directory / SUMS_FILENAME
    if not path.exists():
        report.problems.append(f"no {SUMS_FILENAME}")
        return
    try:
        recorded = parse_sums(path.read_text(encoding="utf-8"))
    except ValueError as exc:
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
    elif recorded[MANIFEST_FILENAME] != file_digest(directory / MANIFEST_FILENAME):
        report.problems.append(
            f"{MANIFEST_FILENAME}: {SUMS_FILENAME} records a digest that does not "
            "match the manifest on disk"
        )

    expected = {output["path"] for output in document["outputs"]} | {MANIFEST_FILENAME}
    for extra in sorted(set(recorded) - expected):
        report.problems.append(f"{SUMS_FILENAME} lists {extra!r}, which the manifest does not")
    for missing in sorted(expected - set(recorded)):
        report.problems.append(f"{SUMS_FILENAME} omits {missing!r}")


def _check_spans(directory: Path, report: VerifyReport) -> None:
    """Re-extract every span from the text it indexes."""
    import hashlib

    for sidecar in sorted(directory.glob("*.labels.jsonl")):
        stem = sidecar.name.removesuffix(".labels.jsonl")
        data_path = _find_data_file(directory, stem)
        if data_path is None:
            report.problems.append(f"{sidecar.name}: no data file named {stem}")
            continue

        texts = _document_texts(data_path)
        for number, line in enumerate(sidecar.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            record = json.loads(line)
            report.documents_checked += 1
            text = texts.get(record["doc_id"])
            if text is None:
                report.problems.append(
                    f"{sidecar.name} line {number}: no document {record['doc_id']}"
                )
                continue
            actual_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if actual_digest != record["text_sha256"]:
                report.problems.append(
                    f"{sidecar.name} line {number}: text_sha256 does not match the document"
                )
                continue
            for span in record["spans"]:
                report.spans_checked += 1
                if span["end"] > len(text) or span["start"] < 0:
                    report.problems.append(
                        f"{sidecar.name} line {number}: span [{span['start']}, {span['end']}) "
                        f"falls outside a {len(text)} character document"
                    )
                elif not text[span["start"] : span["end"]].strip():
                    report.problems.append(
                        f"{sidecar.name} line {number}: span [{span['start']}, "
                        f"{span['end']}) covers only whitespace"
                    )


def _find_data_file(directory: Path, stem: str) -> Path | None:
    for suffix in (".jsonl", ".csv"):
        candidate = directory / f"{stem}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _document_texts(path: Path) -> dict[str, str]:
    """Map document id to text, for whichever field carries the document."""
    texts: dict[str, str] = {}
    if path.suffix != ".jsonl":
        return texts
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        doc_id = next((v for k, v in record.items() if k.endswith("_id")), None)
        if doc_id is None:
            continue
        for key, value in record.items():
            if key in {"body", "description", "text", "note"} and isinstance(value, str):
                texts[str(doc_id)] = value
                break
    return texts


_CANDIDATE = re.compile(r"[A-Z]{2}[0-9]{24}|[0-9]{10,16}")


def _sweep_identifiers(
    directory: Path, validators: dict[str, Validator], report: VerifyReport
) -> None:
    """Invariant 2, checked on the artifacts rather than on the generator.

    Every candidate string in every emitted file is put through every validator.
    A hit means safe mode produced a value a real validator would accept, which is
    the one thing the product promises cannot happen.
    """
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.name in {MANIFEST_FILENAME, SUMS_FILENAME}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for candidate in set(_CANDIDATE.findall(text)):
            for name, validator in validators.items():
                if validator(candidate):
                    report.checksum_valid_identifiers += 1
                    report.problems.append(
                        f"{path.name}: {candidate!r} is a checksum-valid {name} under "
                        "a safe policy; safe mode is the product's safety claim"
                    )


def all_files(directory: Path) -> Iterable[Path]:
    return (p for p in sorted(Path(directory).rglob("*")) if p.is_file())
