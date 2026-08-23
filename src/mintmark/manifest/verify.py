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

import csv
import re
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime
from itertools import islice, pairwise
from pathlib import Path
from typing import Any

import jsonschema

from mintmark.manifest.document import (
    DETERMINISM_CLAIM,
    EXCLUDED_FROM_CLAIM,
    MANIFEST_FILENAME,
    SUPPORTED_PLATFORMS,
    VALIDATOR_WARNING,
    read_manifest,
)
from mintmark.manifest.io import (
    MAX_CONTROL_FILE_BYTES,
    MAX_DATA_FILE_BYTES,
    DatasetIOError,
    DatasetReader,
    strict_json_loads,
)
from mintmark.manifest.safety import identifier_candidates
from mintmark.manifest.sums import SUMS_FILENAME, parse_sums

Validator = Callable[[str], bool]
MAX_SCHEMA_PROBLEMS = 100
MAX_RECORDS_PER_OUTPUT = 1_000_000  # matches MAX_RECORDS_PER_TYPE in packs.model
MAX_RECORD_CHARS = 1 << 20
MAX_SPANS_PER_DOCUMENT = 4096
MAX_VERIFY_DATASET_BYTES = 512 << 20
MAX_VERIFY_PROBLEMS = 1_000


class _ProblemList(list[str]):
    """Bound diagnostics so hostile repetition cannot become a second DoS."""

    def append(self, problem: str) -> None:
        if len(self) < MAX_VERIFY_PROBLEMS:
            super().append(problem)
        elif len(self) == MAX_VERIFY_PROBLEMS:
            super().append(
                f"verification found more than {MAX_VERIFY_PROBLEMS} problems; remaining omitted"
            )


@dataclass(slots=True)
class VerifyReport:
    """Everything verification observed, sound or not."""

    directory: str
    schema_valid: bool = False
    checksums_checked: int = 0
    checksums_matched: int = 0
    identifier_policy: str = "unknown"
    checksum_valid_identifiers: int = 0
    coverage_checked: bool = False
    coverage_targets_checked: int = 0
    documents_checked: int = 0
    spans_checked: int = 0
    taxonomy_pin: str = ""
    dataset_license: str = "unknown"
    attribution: str = ""
    manifest_sha256: str = ""
    authenticity: str = "self-consistency only; no trusted manifest digest supplied"
    problems: list[str] = dataclass_field(default_factory=_ProblemList)

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
            "coverage_checked": self.coverage_checked,
            "coverage_targets_checked": self.coverage_targets_checked,
            "documents_checked": self.documents_checked,
            "spans_checked": self.spans_checked,
            "taxonomy_pin": self.taxonomy_pin,
            "dataset_license": self.dataset_license,
            "attribution": self.attribution,
            "manifest_sha256": self.manifest_sha256,
            "authenticity": self.authenticity,
            "problems": list(self.problems),
        }

    def render(self) -> str:
        lines = [
            f"manifest schema: {'valid' if self.schema_valid else 'INVALID'}",
            f"checksums: {self.checksums_matched}/{self.checksums_checked} match",
            f"identifier policy: {self.identifier_policy} (confirmed)"
            if self.identifier_policy != "unknown"
            else "identifier policy: unknown",
            f"checksum-valid identifiers found: {self.checksum_valid_identifiers}"
            + (
                " (expected under the validator policy)"
                if self.identifier_policy == "validator"
                else ""
            ),
            f"coverage targets: {self.coverage_targets_checked} checked"
            if self.coverage_checked
            else "coverage targets: not checked, this mint overrode its record counts",
            f"taxonomy: {self.taxonomy_pin}",
            f"label alignment: {self.documents_checked} documents, {self.spans_checked} spans",
            f"dataset license: {self.dataset_license}",
            f"attribution: {self.attribution}",
            f"authenticity: {self.authenticity}",
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
    trusted_manifest_sha256: str | None = None,
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
            report.manifest_sha256, _ = reader.digest(
                MANIFEST_FILENAME, max_bytes=MAX_CONTROL_FILE_BYTES
            )
        except (DatasetIOError, OSError, ValueError) as exc:
            report.problems.append(str(exc))
            return report
        if trusted_manifest_sha256 is not None:
            if not re.fullmatch(r"[0-9a-f]{64}", trusted_manifest_sha256):
                report.problems.append(
                    "trusted manifest digest must be 64 lowercase hex characters"
                )
            elif report.manifest_sha256 != trusted_manifest_sha256:
                report.problems.append(
                    "manifest digest does not match the externally trusted digest"
                )
            else:
                report.authenticity = "trusted manifest digest matched"

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
        try:
            _check_validator_warning(document, report)
            _check_checksums(reader, document, report)
            _check_sums_file(reader, document, report)
            primary = _scan_primary_records(reader, document, report, validators)
            label_counts = _check_spans(
                reader,
                document,
                report,
                document_texts=primary.document_texts,
                known_labels=known_labels,
            )
            _check_manifest_claims(document, primary, label_counts, report, known_labels)
            _check_coverage(document, report)
        except Exception as exc:  # verifier boundary: hostile input must become a report
            report.problems.append(f"verification aborted safely: {type(exc).__name__}: {exc}")

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
    total_bytes = sum(output["bytes"] for output in document["outputs"])
    if total_bytes > MAX_VERIFY_DATASET_BYTES:
        report.problems.append(
            f"{MANIFEST_FILENAME}: outputs claim {total_bytes} bytes; aggregate verification "
            f"limit is {MAX_VERIFY_DATASET_BYTES}"
        )
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


def _check_coverage(document: dict[str, Any], report: VerifyReport) -> None:
    """A declared coverage target that was missed is a verification failure.

    The target, the achieved count, and a `met` flag were already written into
    every manifest, and the only thing reading them checked that the flag was
    honest, not that the target was reached. So an evaluation set could ship
    without a whole label and still verify clean.

    The one exemption is a mint whose record counts were overridden: `packcheck`
    mini-mints twenty-five records against targets in the hundreds, and a
    deliberately shrunken run is not a claim the recipe made.
    """
    overrides = document["recipe"]["parameters"].get("overrides", {})
    if "records" in overrides:
        report.coverage_checked = False
        return
    report.coverage_checked = True
    for stat in document["stats"].get("coverage_targets", []):
        report.coverage_targets_checked += 1
        if stat["achieved"] < stat["target"]:
            report.problems.append(
                f"coverage target {stat['label']}={stat['target']} was not met: "
                f"{stat['achieved']} span(s) emitted. An evaluation set short of a "
                "label measures nothing about that label."
            )


def _check_checksums(reader: DatasetReader, document: dict[str, Any], report: VerifyReport) -> None:
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


def _check_sums_file(reader: DatasetReader, document: dict[str, Any], report: VerifyReport) -> None:
    try:
        recorded = parse_sums(reader.read_text(SUMS_FILENAME, max_bytes=MAX_CONTROL_FILE_BYTES))
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
            manifest_digest, _ = reader.digest(MANIFEST_FILENAME, max_bytes=MAX_CONTROL_FILE_BYTES)
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


@dataclass(slots=True)
class _PrimaryScan:
    record_counts: dict[str, int]
    distribution_counts: dict[str, Counter[str]]
    document_texts: dict[str, dict[str, str]]


def _scan_primary_records(
    reader: DatasetReader,
    document: dict[str, Any],
    report: VerifyReport,
    validators: dict[str, Validator],
) -> _PrimaryScan:
    """Stream primary outputs into bounded semantic aggregates."""
    type_outputs: dict[str, str] = {}
    primary_outputs: list[tuple[dict[str, Any], str, str, str]] = []
    for output in document["outputs"]:
        name = output["path"]
        if name.endswith(".labels.jsonl"):
            continue
        if name.endswith(".jsonl"):
            type_name = name.removesuffix(".jsonl")
            fmt = "jsonl"
        elif name.endswith(".csv"):
            type_name = name.removesuffix(".csv")
            fmt = "csv"
        else:
            report.problems.append(f"{name}: unsupported dataset output format")
            continue
        if type_name in type_outputs:
            report.problems.append(
                f"{name}: second primary output for record type {type_name!r} "
                f"(already {type_outputs[type_name]})"
            )
            continue
        type_outputs[type_name] = name
        primary_outputs.append((output, name, type_name, fmt))

    sites_by_type: dict[str, list[tuple[str, str, dict[str, str]]]] = {}
    distribution_counts: dict[str, Counter[str]] = {}
    seen_sites: set[str] = set()
    for distribution in document["stats"]["distributions"]:
        site = distribution["site"]
        if site in seen_sites:
            report.problems.append(f"stats.distributions duplicates site {site!r}")
            continue
        seen_sites.add(site)
        type_name, separator, field_name = site.partition("/")
        if not separator or "/" in field_name or type_name not in type_outputs:
            report.problems.append(f"stats.distributions site {site!r} does not resolve")
            continue
        target = distribution["target"]
        sites_by_type.setdefault(type_name, []).append((site, field_name, target))
        distribution_counts[site] = Counter()

    names = {output["path"] for output in document["outputs"]}
    record_counts: dict[str, int] = {}
    document_texts: dict[str, dict[str, str]] = {}
    for output, name, type_name, fmt in primary_outputs:
        count = 0
        texts: dict[str, str] | None = {} if f"{type_name}.labels.jsonl" in names else None

        try:
            if fmt == "jsonl":
                lines = reader.iter_text_lines(
                    name,
                    max_bytes=MAX_DATA_FILE_BYTES,
                    max_line_chars=MAX_RECORD_CHARS,
                )
                for number, line in enumerate(lines, start=1):
                    if not line.strip():
                        continue
                    try:
                        parsed = strict_json_loads(line, context=f"{name} line {number}")
                    except ValueError as exc:
                        report.problems.append(str(exc))
                        continue
                    if not isinstance(parsed, dict):
                        report.problems.append(f"{name} line {number}: record is not a JSON object")
                        continue
                    count += 1
                    _observe_primary_record(
                        name,
                        number,
                        parsed,
                        type_name,
                        sites_by_type,
                        distribution_counts,
                        texts,
                        validators,
                        report,
                    )
                    if count > MAX_RECORDS_PER_OUTPUT:
                        report.problems.append(f"{name}: exceeds the record-count limit")
                        break
            else:
                previous_limit = csv.field_size_limit()
                csv.field_size_limit(MAX_RECORD_CHARS)
                try:
                    parsed_rows = csv.reader(
                        reader.iter_text_lines(
                            name,
                            max_bytes=MAX_DATA_FILE_BYTES,
                            max_line_chars=MAX_RECORD_CHARS,
                        )
                    )
                    try:
                        header = next(parsed_rows)
                    except StopIteration:
                        header = []
                    if (
                        not header
                        or any(not field for field in header)
                        or len(set(header)) != len(header)
                    ):
                        report.problems.append(f"{name}: CSV header is missing or ambiguous")
                    elif len(header) > 256:
                        report.problems.append(f"{name}: CSV header exceeds the field-count limit")
                    else:
                        for values in parsed_rows:
                            number = parsed_rows.line_num
                            if len(values) != len(header):
                                report.problems.append(
                                    f"{name} row {number}: {len(values)} fields for "
                                    f"{len(header)} headers"
                                )
                                continue
                            record = dict(zip(header, values, strict=True))
                            count += 1
                            _observe_primary_record(
                                name,
                                number,
                                record,
                                type_name,
                                sites_by_type,
                                distribution_counts,
                                texts,
                                validators,
                                report,
                            )
                            if count > MAX_RECORDS_PER_OUTPUT:
                                report.problems.append(f"{name}: exceeds the record-count limit")
                                break
                finally:
                    csv.field_size_limit(previous_limit)
        except (DatasetIOError, OSError, csv.Error, ValueError) as exc:
            report.problems.append(f"{name}: parse failed safely: {exc}")

        record_counts[type_name] = count
        if texts is not None:
            document_texts[name] = texts
        if output["records"] != count:
            report.problems.append(f"{name}: records claim {output['records']}, actual {count}")

    return _PrimaryScan(record_counts, distribution_counts, document_texts)


def _observe_primary_record(
    name: str,
    number: int,
    record: Mapping[str, object],
    type_name: str,
    sites_by_type: dict[str, list[tuple[str, str, dict[str, str]]]],
    distribution_counts: dict[str, Counter[str]],
    texts: dict[str, str] | None,
    validators: dict[str, Validator],
    report: VerifyReport,
) -> None:
    for site, field_name, target in sites_by_type.get(type_name, []):
        value = record.get(field_name)
        if value is not None and str(value) in target:
            distribution_counts[site][str(value)] += 1
        elif value is not None:
            report.problems.append(
                f"stats.distributions site {site!r} omits observed value {value!r}"
            )

    if texts is not None:
        doc_id = next((value for key, value in record.items() if key.endswith("_id")), None)
        text = next(
            (
                value
                for key, value in record.items()
                if key in {"body", "description", "text", "note"} and isinstance(value, str)
            ),
            None,
        )
        if doc_id is not None and text is not None:
            document_id = str(doc_id)
            if document_id in texts:
                report.problems.append(
                    f"{name} line {number}: duplicate document id {document_id!r}"
                )
            else:
                texts[document_id] = text

    _sweep_record(name, number, record, validators, report)


def _scaled(decimal_string: str) -> int:
    whole, separator, fraction = decimal_string.partition(".")
    if not whole.isdigit() or (separator and not fraction.isdigit()):
        raise ValueError(f"invalid decimal claim {decimal_string!r}")
    fraction = (fraction + "0000")[:4]
    return int(whole) * 10_000 + int(fraction)


def _proportion(count: int, total: int) -> str:
    if total == 0:
        return "0"
    scaled = (count * 10_000 + total // 2) // total
    return f"{scaled // 10_000}.{scaled % 10_000:04d}"


def _check_manifest_claims(
    document: dict[str, Any],
    primary: _PrimaryScan,
    label_counts: Counter[str],
    report: VerifyReport,
    known_labels: frozenset[str],
) -> None:
    """Re-derive record, distribution, coverage, terms, and fixed-contract claims."""
    actual_counts = primary.record_counts
    if document["stats"]["record_counts"] != actual_counts:
        report.problems.append("stats.record_counts does not match parsed primary outputs")
    if document["recipe"]["parameters"]["records"] != actual_counts:
        report.problems.append("recipe.parameters.records does not match parsed primary outputs")

    for distribution in document["stats"]["distributions"]:
        site = distribution["site"]
        if site not in primary.distribution_counts:
            continue
        target = distribution["target"]
        observed = primary.distribution_counts[site]
        total = sum(observed.values())
        achieved = {key: _proportion(observed[key], total) for key in sorted(target)}
        if distribution["achieved"] != achieved:
            report.problems.append(
                f"stats.distributions site {site!r} has fabricated achieved values"
            )
        within = all(abs(_scaled(achieved[key]) - _scaled(target[key])) <= 200 for key in target)
        if distribution["within_tolerance"] is not within:
            report.problems.append(f"stats.distributions site {site!r} has a false tolerance flag")

    actual_coverage = dict(sorted(label_counts.items()))
    if document["entity_coverage"] != actual_coverage:
        report.problems.append("entity_coverage does not match valid sidecar spans")
    unknown_coverage = sorted(set(document["entity_coverage"]) - known_labels)
    if unknown_coverage:
        report.problems.append(f"entity_coverage contains unknown labels {unknown_coverage}")
    seen_labels: set[str] = set()
    for coverage in document["stats"].get("coverage_targets", []):
        label = coverage["label"]
        if label in seen_labels:
            report.problems.append(f"stats.coverage_targets duplicates label {label!r}")
            continue
        seen_labels.add(label)
        actual = label_counts[label]
        if label not in known_labels:
            report.problems.append(f"stats.coverage_targets contains unknown label {label!r}")
        if coverage["achieved"] != actual:
            report.problems.append(f"stats.coverage_targets {label!r} has a false achieved count")
        if coverage["met"] is not (actual >= coverage["target"]):
            report.problems.append(f"stats.coverage_targets {label!r} has a false met flag")

    attribution = (
        f"{document['pack']['name']} {document['pack']['version']} reference dataset "
        f"(recipe {document['recipe']['name']}, seed {document['seed']}), lokomotifai, "
        f"licensed {document['license']['datasets']}"
    )
    if document["license"]["attribution"] != attribution:
        report.problems.append("license.attribution is inconsistent with the dataset identity")
    determinism = document["determinism"]
    if determinism["claim"] != DETERMINISM_CLAIM:
        report.problems.append("determinism.claim is not the engine's fixed claim")
    if determinism["platforms"] != list(SUPPORTED_PLATFORMS):
        report.problems.append("determinism.platforms differs from the engine contract")
    if determinism["excluded"] != list(EXCLUDED_FROM_CLAIM):
        report.problems.append("determinism.excluded differs from the engine contract")
    try:
        created = datetime.fromisoformat(document["provenance"]["created_utc"])
    except ValueError:
        report.problems.append("provenance.created_utc is not an ISO-8601 timestamp")
    else:
        if created.tzinfo is None:
            report.problems.append("provenance.created_utc has no timezone")
    invocation = document["provenance"]["invocation"]
    if any(character in invocation for character in ("\x00", "\r", "\n")):
        report.problems.append("provenance.invocation contains control characters")


def _check_spans(
    reader: DatasetReader,
    document: dict[str, Any],
    report: VerifyReport,
    *,
    document_texts: dict[str, dict[str, str]],
    known_labels: frozenset[str],
) -> Counter[str]:
    """Re-extract every span from the text it indexes."""
    import hashlib

    names = {output["path"] for output in document["outputs"]}
    declared_counts = {output["path"]: output["records"] for output in document["outputs"]}
    label_counts: Counter[str] = Counter()
    for sidecar_name in sorted(name for name in names if name.endswith(".labels.jsonl")):
        stem = sidecar_name.removesuffix(".labels.jsonl")
        data_name = _find_data_file(names, stem)
        if data_name is None:
            report.problems.append(f"{sidecar_name}: no data file named {stem}")
            continue

        texts = document_texts.pop(data_name, {})
        sidecar_ids: set[str] = set()
        sidecar_records = 0
        for number, line in enumerate(_stream_lines(reader, sidecar_name, report), start=1):
            if not line.strip():
                continue
            sidecar_records += 1
            if sidecar_records > MAX_RECORDS_PER_OUTPUT:
                report.problems.append(f"{sidecar_name}: exceeds the record-count limit")
                break
            try:
                record = strict_json_loads(line, context=f"{sidecar_name} line {number}")
            except ValueError as exc:
                report.problems.append(str(exc))
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
            if set(record) != {"doc_id", "text_sha256", "spans"}:
                report.problems.append(f"{sidecar_name} line {number}: unsupported sidecar fields")
                continue
            if len(record["spans"]) > MAX_SPANS_PER_DOCUMENT:
                report.problems.append(f"{sidecar_name} line {number}: too many spans")
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
                if set(span) != {"start", "end", "label"}:
                    report.problems.append(f"{sidecar_name} line {number}: unsupported span fields")
                    continue
                if span["end"] > len(text) or span["start"] < 0 or span["start"] >= span["end"]:
                    report.problems.append(
                        f"{sidecar_name} line {number}: span [{span['start']}, {span['end']}) "
                        f"falls outside a {len(text)} character document"
                    )
                    continue
                if not text[span["start"] : span["end"]].strip():
                    report.problems.append(
                        f"{sidecar_name} line {number}: span [{span['start']}, "
                        f"{span['end']}) covers only whitespace"
                    )
                    continue
                intervals.append((span["start"], span["end"]))
                label_counts[label] += 1
            ordered = sorted(intervals)
            if len(set(ordered)) != len(ordered):
                report.problems.append(f"{sidecar_name} line {number}: duplicate spans")
            for earlier, later in pairwise(ordered):
                if later[0] < earlier[1]:
                    report.problems.append(f"{sidecar_name} line {number}: overlapping spans")
        for missing in sorted(set(texts) - sidecar_ids):
            report.problems.append(f"{sidecar_name}: omits document {missing!r}")
        actual_records = len(sidecar_ids)
        if declared_counts[sidecar_name] != actual_records:
            report.problems.append(
                f"{sidecar_name}: records claim {declared_counts[sidecar_name]}, "
                f"actual {actual_records}"
            )
    return label_counts


def _stream_lines(reader: DatasetReader, name: str, report: VerifyReport) -> Iterator[str]:
    try:
        yield from reader.iter_text_lines(
            name,
            max_bytes=MAX_DATA_FILE_BYTES,
            max_line_chars=MAX_RECORD_CHARS,
        )
    except (DatasetIOError, OSError, ValueError) as exc:
        report.problems.append(str(exc))


def _find_data_file(names: set[str], stem: str) -> str | None:
    for suffix in (".jsonl", ".csv"):
        candidate = f"{stem}{suffix}"
        if candidate in names:
            return candidate
    return None


def _sweep_record(
    name: str,
    number: int,
    record: Mapping[str, object],
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
    for candidate in identifier_candidates(record):
        for validator_name, validator in validators.items():
            if validator(candidate):
                report.checksum_valid_identifiers += 1
                if report.identifier_policy == "safe":
                    report.problems.append(
                        f"{name} line {number}: contains a checksum-valid "
                        f"{validator_name} under a safe policy; safe mode is the "
                        "product's safety claim"
                    )
