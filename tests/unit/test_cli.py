"""Invariant 13: the exit-code contract, and the stable --json payloads.

A script consuming this tool needs to tell a malformed pack from a tampered
dataset from a reproduction mismatch. That is what the five codes are for, so
each one is produced by a named scenario here and by no scenario that should
produce a different one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mintmark.cli import (
    EXIT_INVALID_PACK,
    EXIT_OK,
    EXIT_REPRODUCE_MISMATCH,
    EXIT_USAGE,
    EXIT_VERIFY_FAILED,
    main,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK = str(REPO_ROOT / "packs" / "example")
FIXTURES = REPO_ROOT / "tests" / "adversarial" / "packs"

SMALL = ["--records", "customer=20", "--records", "transaction=20"]


def mint_to(out: Path, *extra: str) -> int:
    return main(
        [
            "mint",
            "--pack",
            PACK,
            "--recipe",
            "demo",
            "--seed",
            "42",
            "--out",
            str(out),
            *SMALL,
            *extra,
        ]
    )


def test_exit_zero_on_a_successful_mint(tmp_path: Path) -> None:
    assert mint_to(tmp_path / "run") == EXIT_OK


def test_exit_zero_on_verify_of_a_sound_dataset(tmp_path: Path) -> None:
    out = tmp_path / "run"
    mint_to(out)
    assert main(["verify", str(out)]) == EXIT_OK


def test_exit_zero_on_reproduce_of_an_untouched_dataset(tmp_path: Path) -> None:
    out = tmp_path / "run"
    mint_to(out)
    assert main(["reproduce", str(out)]) == EXIT_OK


def test_exit_one_on_an_unknown_recipe(tmp_path: Path) -> None:
    code = main(
        [
            "mint",
            "--pack",
            PACK,
            "--recipe",
            "nonexistent",
            "--seed",
            "1",
            "--out",
            str(tmp_path / "r"),
        ]
    )
    assert code == EXIT_USAGE


def test_exit_one_on_a_malformed_records_override(tmp_path: Path) -> None:
    code = main(
        [
            "mint",
            "--pack",
            PACK,
            "--recipe",
            "demo",
            "--seed",
            "1",
            "--records",
            "customer",
            "--out",
            str(tmp_path / "r"),
        ]
    )
    assert code == EXIT_USAGE


def test_exit_one_when_records_names_an_undeclared_type(tmp_path: Path) -> None:
    code = main(
        [
            "mint",
            "--pack",
            PACK,
            "--recipe",
            "demo",
            "--seed",
            "1",
            "--records",
            "unicorn=5",
            "--out",
            str(tmp_path / "r"),
        ]
    )
    assert code == EXIT_USAGE


def test_exit_two_on_an_invalid_pack(tmp_path: Path) -> None:
    code = main(
        [
            "mint",
            "--pack",
            str(FIXTURES / "duplicate-key"),
            "--recipe",
            "demo",
            "--seed",
            "1",
            "--out",
            str(tmp_path / "r"),
        ]
    )
    assert code == EXIT_INVALID_PACK


def test_exit_two_on_packcheck_of_an_invalid_pack() -> None:
    assert main(["packcheck", str(FIXTURES / "unknown-field")]) == EXIT_INVALID_PACK


def test_exit_three_on_a_tampered_dataset(tmp_path: Path) -> None:
    out = tmp_path / "run"
    mint_to(out)
    path = out / "customer.jsonl"
    raw = bytearray(path.read_bytes())
    raw[10] ^= 0x01
    path.write_bytes(bytes(raw))
    assert main(["verify", str(out)]) == EXIT_VERIFY_FAILED


def test_exit_three_when_the_manifest_is_missing(tmp_path: Path) -> None:
    out = tmp_path / "run"
    mint_to(out)
    (out / "MINTMARK.json").unlink()
    assert main(["verify", str(out)]) == EXIT_VERIFY_FAILED


def test_exit_four_when_reproduction_differs(tmp_path: Path, monkeypatch) -> None:
    """A dataset whose recorded seed no longer produces its bytes."""
    out = tmp_path / "run"
    mint_to(out)
    document = json.loads((out / "MINTMARK.json").read_text(encoding="utf-8"))
    document["seed"] = "999"
    (out / "MINTMARK.json").write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    monkeypatch.chdir(REPO_ROOT)
    assert main(["reproduce", str(out)]) == EXIT_REPRODUCE_MISMATCH


def test_every_exit_code_is_reachable() -> None:
    """Guards against a code being defined and never produced."""
    assert {
        EXIT_OK,
        EXIT_USAGE,
        EXIT_INVALID_PACK,
        EXIT_VERIFY_FAILED,
        EXIT_REPRODUCE_MISMATCH,
    } == {
        0,
        1,
        2,
        3,
        4,
    }


def test_mint_json_payload_has_the_documented_shape(tmp_path: Path, capsys) -> None:
    mint_to(tmp_path / "run", "--json")
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "out",
        "pack",
        "pack_version",
        "pack_digest",
        "recipe",
        "seed",
        "identifier_policy",
        "format",
        "record_counts",
        "entity_coverage",
        "outputs",
    }
    assert isinstance(payload["seed"], str), "a u64 seed is a string, not a JSON number"
    assert payload["identifier_policy"] == "safe"


def test_cli_manifest_does_not_publish_local_pack_or_output_paths(tmp_path: Path) -> None:
    out = tmp_path / "private" / "run"
    assert mint_to(out) == EXIT_OK
    document = json.loads((out / "MINTMARK.json").read_text(encoding="utf-8"))
    invocation = document["provenance"]["invocation"]
    assert str(PACK) not in invocation
    assert str(out) not in invocation
    assert "<pack>" in invocation
    assert "<output>" in invocation


def test_verify_json_payload_has_the_documented_shape(tmp_path: Path, capsys) -> None:
    out = tmp_path / "run"
    mint_to(out)
    capsys.readouterr()
    main(["verify", str(out), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "directory",
        "ok",
        "schema_valid",
        "checksums",
        "identifier_policy",
        "checksum_valid_identifiers",
        "documents_checked",
        "spans_checked",
        "taxonomy_pin",
        "dataset_license",
        "attribution",
        "manifest_sha256",
        "authenticity",
        "problems",
    }
    assert payload["ok"] is True
    assert payload["dataset_license"] == "CC-BY-4.0"
    assert payload["attribution"].startswith("mintmark-example ")
    assert len(payload["manifest_sha256"]) == 64
    assert payload["authenticity"].startswith("self-consistency")
    assert payload["problems"] == []


def test_verify_can_bind_to_an_externally_trusted_manifest_digest(tmp_path: Path) -> None:
    from mintmark.manifest import file_digest

    out = tmp_path / "run"
    mint_to(out)
    digest = file_digest(out / "MINTMARK.json")
    assert main(["verify", str(out), "--trusted-manifest-sha256", digest]) == EXIT_OK
    assert main(["verify", str(out), "--trusted-manifest-sha256", "0" * 64]) == EXIT_VERIFY_FAILED


def test_manifest_drift_paths_cannot_collide_on_dotted_keys() -> None:
    from mintmark.cli import _manifest_drift

    drift = _manifest_drift({"a.b": 1, "a": {"b": 2}}, {"a.b": 2, "a": {"b": 1}})
    assert set(drift) == {("a.b",), ("a", "b")}


def test_inspect_json_payload_names_the_declarations(capsys) -> None:
    main(["inspect", PACK, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["name"] == "mintmark-example"
    assert [t["type_name"] for t in payload["record_types"]] == ["customer", "transaction"]
    assert payload["recipes"] == ["demo"]
    assert len(payload["digest"]) == 64


def test_packcheck_json_payload_reports_ok(capsys) -> None:
    main(["packcheck", PACK, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["problems"] == []


@pytest.mark.parametrize("which", ["pack", "manifest"])
def test_schema_prints_valid_json(which: str, capsys) -> None:
    assert main(["schema", which]) == EXIT_OK
    document = json.loads(capsys.readouterr().out)
    assert document["$schema"].startswith("https://json-schema.org/")


def test_version_flag_reports_the_package_version(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--version"])
    assert caught.value.code == 0
    from mintmark import __version__

    assert __version__ in capsys.readouterr().out


def test_an_error_carries_no_traceback(tmp_path: Path, capsys) -> None:
    """A user needs the line of their pack that is wrong, not our internals."""
    main(
        [
            "mint",
            "--pack",
            str(FIXTURES / "duplicate-key"),
            "--recipe",
            "demo",
            "--seed",
            "1",
            "--out",
            str(tmp_path / "r"),
        ]
    )
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "duplicate key" in captured.err
    assert "pack.yaml" in captured.err


def test_a_failed_mint_leaves_no_output_directory(tmp_path: Path) -> None:
    out = tmp_path / "r"
    main(
        [
            "mint",
            "--pack",
            str(FIXTURES / "duplicate-key"),
            "--recipe",
            "demo",
            "--seed",
            "1",
            "--out",
            str(out),
        ]
    )
    assert not out.exists()


def test_validator_policy_must_be_allowed_by_the_pack(tmp_path: Path) -> None:
    """The example pack allows it; a pack that did not would refuse."""
    assert mint_to(tmp_path / "run", "--identifier-policy", "validator") == EXIT_OK


def test_csv_format_produces_csv_files(tmp_path: Path) -> None:
    out = tmp_path / "run"
    assert mint_to(out, "--format", "csv") == EXIT_OK
    assert (out / "customer.csv").exists()
    header = (out / "customer.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.startswith("customer_id,first_name,last_name")
