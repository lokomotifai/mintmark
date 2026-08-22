"""Invariant 3: verification fails on any single-byte tamper.

The manifest is the reason a directory of files counts as evidence. If a dataset
can be altered and still verify, the manifest is decoration.

Every case here alters exactly one byte, or removes exactly one thing, and
asserts that verification notices and says what it noticed.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from mintmark.cli import (
    EXIT_OK,
    EXIT_REPRODUCE_MISMATCH,
    EXIT_VERIFY_FAILED,
    main,
)
from mintmark.manifest import (
    MANIFEST_FILENAME,
    SUMS_FILENAME,
    VALIDATOR_WARNING,
    file_digest,
    render_sums,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK = REPO_ROOT / "packs" / "example"


@pytest.fixture(scope="module")
def minted(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One small mint, reused by every tamper case through a copy."""
    out = tmp_path_factory.mktemp("pristine") / "run"
    assert (
        main(
            [
                "mint",
                "--pack",
                str(PACK),
                "--recipe",
                "demo",
                "--seed",
                "42",
                "--records",
                "customer=30",
                "--records",
                "transaction=30",
                "--out",
                str(out),
            ]
        )
        == EXIT_OK
    )
    return out


@pytest.fixture
def dataset(minted: Path, tmp_path: Path) -> Path:
    target = tmp_path / "run"
    shutil.copytree(minted, target)
    return target


def reseal_output(dataset: Path, output_name: str) -> None:
    """Update self-referential hashes so semantic verification gets exercised."""
    manifest_path = dataset / MANIFEST_FILENAME
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    sums: dict[str, str] = {}
    for output in document["outputs"]:
        output_path = dataset / output["path"]
        if output["path"] == output_name:
            output["sha256"] = file_digest(output_path)
            output["bytes"] = output_path.stat().st_size
        sums[output["path"]] = output["sha256"]
    manifest_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    sums[MANIFEST_FILENAME] = file_digest(manifest_path)
    (dataset / SUMS_FILENAME).write_text(render_sums(sums), encoding="utf-8")


def reseal_manifest(dataset: Path) -> None:
    manifest_path = dataset / MANIFEST_FILENAME
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    sums = {output["path"]: output["sha256"] for output in document["outputs"]}
    sums[MANIFEST_FILENAME] = file_digest(manifest_path)
    (dataset / SUMS_FILENAME).write_text(render_sums(sums), encoding="utf-8")


def test_the_pristine_dataset_verifies(dataset: Path) -> None:
    """Otherwise every tamper below could be failing for the wrong reason."""
    assert main(["verify", str(dataset)]) == EXIT_OK


@pytest.mark.adversarial
def test_a_single_flipped_byte_in_a_data_file_is_caught(dataset: Path) -> None:
    path = dataset / "customer.jsonl"
    raw = bytearray(path.read_bytes())
    raw[100] = raw[100] ^ 0x01
    path.write_bytes(bytes(raw))
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_a_single_flipped_byte_in_a_sidecar_is_caught(dataset: Path) -> None:
    path = dataset / "transaction.labels.jsonl"
    raw = bytearray(path.read_bytes())
    raw[50] = raw[50] ^ 0x01
    path.write_bytes(bytes(raw))
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_an_altered_checksum_in_the_manifest_is_caught(dataset: Path) -> None:
    path = dataset / MANIFEST_FILENAME
    document = json.loads(path.read_text(encoding="utf-8"))
    original = document["outputs"][0]["sha256"]
    document["outputs"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED
    assert original != "0" * 64


@pytest.mark.adversarial
def test_an_altered_sums_file_is_caught(dataset: Path) -> None:
    path = dataset / SUMS_FILENAME
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = "0" * 64 + "  " + lines[0].split("  ", 1)[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_a_removed_manifest_is_caught(dataset: Path) -> None:
    (dataset / MANIFEST_FILENAME).unlink()
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_a_removed_data_file_is_caught(dataset: Path) -> None:
    (dataset / "customer.jsonl").unlink()
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_an_added_file_is_caught(dataset: Path) -> None:
    """A file nobody vouched for is as much a problem as an altered one."""
    (dataset / "extra.jsonl").write_text('{"smuggled":true}\n', encoding="utf-8")
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_manifest_output_path_cannot_escape_the_dataset(dataset: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.jsonl"
    outside.write_text("secret\n", encoding="utf-8")
    path = dataset / MANIFEST_FILENAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["outputs"][0]["path"] = "../outside.jsonl"
    path.write_text(json.dumps(document) + "\n", encoding="utf-8")

    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED
    assert outside.read_text(encoding="utf-8") == "secret\n"


@pytest.mark.adversarial
def test_duplicate_manifest_output_paths_are_rejected(dataset: Path) -> None:
    path = dataset / MANIFEST_FILENAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["outputs"].append(dict(document["outputs"][0]))
    path.write_text(json.dumps(document) + "\n", encoding="utf-8")
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_duplicate_checksum_paths_are_rejected(dataset: Path) -> None:
    path = dataset / SUMS_FILENAME
    first = path.read_text(encoding="utf-8").splitlines()[0]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(first + "\n")
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_output_symlink_is_not_followed(dataset: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.jsonl"
    outside.write_text("do not read\n", encoding="utf-8")
    output = dataset / "customer.jsonl"
    output.unlink()
    output.symlink_to(outside)
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED
    assert outside.read_text(encoding="utf-8") == "do not read\n"


@pytest.mark.adversarial
def test_sums_symlink_is_not_followed(dataset: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.write_text("sensitive material\n", encoding="utf-8")
    sums = dataset / SUMS_FILENAME
    sums.unlink()
    sums.symlink_to(outside)
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_special_file_is_rejected_without_blocking(dataset: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("named pipes are unavailable")
    output = dataset / "customer.jsonl"
    output.unlink()
    os.mkfifo(output)
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_duplicate_manifest_json_keys_fail_closed(dataset: Path) -> None:
    (dataset / MANIFEST_FILENAME).write_text('{"mintmark": {}, "mintmark": {}}\n', encoding="utf-8")
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_oversized_manifest_fails_with_a_verification_result(dataset: Path) -> None:
    (dataset / MANIFEST_FILENAME).write_text(" " * ((4 << 20) + 1), encoding="utf-8")
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_dataset_reader_detects_a_second_file_version(dataset: Path) -> None:
    from mintmark.manifest.io import DatasetIOError, DatasetReader

    name = "customer.jsonl"
    replacement = dataset / "replacement"
    replacement.write_bytes((dataset / name).read_bytes())
    with DatasetReader(dataset) as reader:
        reader.digest(name)
        replacement.replace(dataset / name)
        with pytest.raises(DatasetIOError, match="different file version"):
            reader.read_bytes(name, max_bytes=256 << 20)


@pytest.mark.adversarial
def test_duplicate_keys_in_data_records_are_rejected_after_resealing(dataset: Path) -> None:
    from mintmark.api import verify

    path = dataset / "customer.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    key = next(iter(first))
    lines[0] = lines[0][:-1] + f",{json.dumps(key)}:{json.dumps(first[key])}}}"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    reseal_output(dataset, path.name)

    report = verify(dataset)
    assert not report.ok
    assert any("duplicate object key" in problem for problem in report.problems)


@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        ("output_records", "records claim"),
        ("stats_records", "stats.record_counts"),
        ("distribution", "fabricated achieved"),
        ("coverage", "entity_coverage"),
        ("attribution", "license.attribution"),
        ("determinism", "determinism.claim"),
    ],
)
@pytest.mark.adversarial
def test_resealed_fabricated_manifest_claims_are_rederived(
    dataset: Path, claim: str, expected: str
) -> None:
    from mintmark.api import verify

    path = dataset / MANIFEST_FILENAME
    document = json.loads(path.read_text(encoding="utf-8"))
    if claim == "output_records":
        document["outputs"][0]["records"] += 1
    elif claim == "stats_records":
        first = next(iter(document["stats"]["record_counts"]))
        document["stats"]["record_counts"][first] += 1
    elif claim == "distribution":
        distribution = document["stats"]["distributions"][0]
        distribution["achieved"] = dict.fromkeys(distribution["achieved"], "0")
    elif claim == "coverage":
        first = next(iter(document["entity_coverage"]))
        document["entity_coverage"][first] += 1
    elif claim == "attribution":
        document["license"]["attribution"] = "fabricated attribution"
    else:
        document["determinism"]["claim"] = "all files are always identical"
    path.write_text(json.dumps(document, ensure_ascii=False) + "\n", encoding="utf-8")
    reseal_manifest(dataset)

    report = verify(dataset)
    assert not report.ok
    assert any(expected in problem for problem in report.problems), report.problems


@pytest.mark.adversarial
def test_a_shifted_span_offset_is_caught(dataset: Path) -> None:
    """The sidecar's own digest binds spans to the text they index."""
    path = dataset / "transaction.labels.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    if not record["spans"]:
        pytest.skip("the first document carries no spans")
    record["spans"][0]["end"] += 5000
    lines[0] = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # The checksum catches the edit first, which is correct; both are failures.
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_unknown_sidecar_label_fails_even_when_checksums_are_resealed(dataset: Path) -> None:
    from mintmark.api import verify

    path = dataset / "transaction.labels.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        record = json.loads(line)
        if record["spans"]:
            record["spans"][0]["label"] = "UNDECLARED"
            lines[index] = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            break
    else:
        pytest.skip("fixture emitted no spans")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    reseal_output(dataset, path.name)

    report = verify(dataset)
    assert not report.ok
    assert any("unknown taxonomy label" in problem for problem in report.problems)


@pytest.mark.adversarial
def test_duplicate_sidecar_document_fails_when_checksums_are_resealed(dataset: Path) -> None:
    from mintmark.api import verify

    path = dataset / "transaction.labels.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join([*lines, lines[0]]) + "\n", encoding="utf-8")
    reseal_output(dataset, path.name)

    report = verify(dataset)
    assert not report.ok
    assert any("duplicate document" in problem for problem in report.problems)


@pytest.mark.adversarial
def test_omitted_sidecar_document_fails_when_checksums_are_resealed(dataset: Path) -> None:
    from mintmark.api import verify

    path = dataset / "transaction.labels.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    reseal_output(dataset, path.name)

    report = verify(dataset)
    assert not report.ok
    assert any("omits document" in problem for problem in report.problems)


@pytest.mark.adversarial
def test_a_stripped_validator_warning_is_caught(tmp_path: Path) -> None:
    """This is how a checksum-valid dataset would circulate unlabeled."""
    out = tmp_path / "validator-run"
    assert (
        main(
            [
                "mint",
                "--pack",
                str(PACK),
                "--recipe",
                "demo",
                "--seed",
                "7",
                "--identifier-policy",
                "validator",
                "--records",
                "customer=10",
                "--records",
                "transaction=10",
                "--out",
                str(out),
            ]
        )
        == EXIT_OK
    )

    document = json.loads((out / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert document["validator_warning"] == VALIDATOR_WARNING
    assert main(["verify", str(out)]) == EXIT_OK

    del document["validator_warning"]
    (out / MANIFEST_FILENAME).write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    assert main(["verify", str(out)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_an_altered_validator_warning_is_caught(tmp_path: Path) -> None:
    out = tmp_path / "validator-run"
    main(
        [
            "mint",
            "--pack",
            str(PACK),
            "--recipe",
            "demo",
            "--seed",
            "7",
            "--identifier-policy",
            "validator",
            "--records",
            "customer=10",
            "--records",
            "transaction=10",
            "--out",
            str(out),
        ]
    )
    path = out / MANIFEST_FILENAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["validator_warning"] = "This dataset is completely safe."
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert main(["verify", str(path.parent)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_a_warning_under_a_safe_policy_is_caught(dataset: Path) -> None:
    """The warning means something. It cannot appear where it does not apply."""
    path = dataset / MANIFEST_FILENAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["validator_warning"] = VALIDATOR_WARNING
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


@pytest.mark.adversarial
def test_an_altered_taxonomy_pin_is_caught(dataset: Path) -> None:
    path = dataset / MANIFEST_FILENAME
    document = json.loads(path.read_text(encoding="utf-8"))
    document["taxonomy"]["pin_digest"] = "f" * 64
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert main(["verify", str(dataset)]) == EXIT_VERIFY_FAILED


def test_reproduce_detects_a_changed_data_file(dataset: Path) -> None:
    """A tamper that also updated the checksums would still fail reproduction."""
    path = dataset / "customer.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["first_name"] = "Değiştirildi"
    lines[0] = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest_path = dataset / MANIFEST_FILENAME
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    sums = {}
    for output in document["outputs"]:
        if output["path"] == "customer.jsonl":
            output["sha256"] = file_digest(path)
            output["bytes"] = path.stat().st_size
        sums[output["path"]] = output["sha256"]
    manifest_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    sums[MANIFEST_FILENAME] = file_digest(manifest_path)
    (dataset / SUMS_FILENAME).write_text(render_sums(sums), encoding="utf-8")

    # Checksums now agree with the altered file, so verify passes.
    assert main(["verify", str(dataset)]) == EXIT_OK
    # Reproduction re-derives the data and does not.
    assert main(["reproduce", str(dataset)]) == EXIT_REPRODUCE_MISMATCH


def test_reproduce_refuses_an_altered_sums_file(dataset: Path) -> None:
    path = dataset / SUMS_FILENAME
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[0] = "0" * 64 + "  " + lines[0].split("  ", 1)[1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert main(["reproduce", str(dataset)]) == EXIT_REPRODUCE_MISMATCH


def test_reproduce_refuses_an_unlisted_extra_file(dataset: Path) -> None:
    (dataset / "extra.jsonl").write_text("{}\n", encoding="utf-8")
    assert main(["reproduce", str(dataset)]) == EXIT_REPRODUCE_MISMATCH
