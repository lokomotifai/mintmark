"""Invariant 4: every rejection rule aborts, and aborts for its own reason.

A pack is untrusted input from another repository. The whole safety argument
rests on unknown input failing closed, so each rule gets a fixture that violates
exactly it, and the test asserts which rule fired rather than only that something
did.

That distinction matters more than it looks. A fixture meant to test merge keys
that happens to fail on a duplicate key instead still turns the suite green,
while the merge key rule goes untested forever.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import jsonschema
import pytest
import yaml

from mintmark.packs.loader import MAX_YAML_BYTES, MAX_YAML_DEPTH, PackError, load_yaml
from mintmark.packs.model import load_pack
from mintmark.packs.semver import parse_range

FIXTURES = Path(__file__).resolve().parent / "packs"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "pack.schema.json"
SCHEMA = yaml.safe_load(SCHEMA_PATH.read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
EXAMPLE_PACK = SCHEMA_PATH.parent.parent / "packs" / "example"

# Rules the strict loader enforces before a schema ever sees the document.
LOADER_RULES = {
    "duplicate-key": "duplicate key",
    "anchor": "anchor",
    "alias": "alias",
    "merge-key": "merge keys are not allowed",
    "multiple-documents": "documents in one file",
    "non-mapping-root": "expected a mapping",
    "empty-file": "must declare something",
    "tab-indentation": "tabs may not be used",
}

# Rules the schema enforces once the document is structurally sound.
SCHEMA_RULES = [
    "unknown-field",
    "missing-schema-version",
    "wrong-locale",
    "bad-name-pattern",
    "float-weight",
]


def test_the_baseline_fixture_is_actually_valid() -> None:
    """Otherwise every rejection below could be passing for the wrong reason."""
    document = load_yaml(FIXTURES / "valid" / "pack.yaml")
    VALIDATOR.validate(document)
    assert document["name"] == "mintmark-fixture"


def test_every_fixture_directory_has_a_test() -> None:
    """A fixture nobody asserts against is decoration."""
    present = {p.name for p in FIXTURES.iterdir() if p.is_dir()}
    covered = set(LOADER_RULES) | set(SCHEMA_RULES) | {"valid", "open-ended-requires-core"}
    assert present == covered, f"uncovered fixtures: {present - covered}"


@pytest.mark.adversarial
@pytest.mark.parametrize(("fixture", "expected"), sorted(LOADER_RULES.items()))
def test_loader_rule_fires_for_its_own_reason(fixture: str, expected: str) -> None:
    with pytest.raises(PackError) as caught:
        load_yaml(FIXTURES / fixture / "pack.yaml")

    message = str(caught.value)
    assert expected in message, f"{fixture} failed, but not for its own rule: {message}"
    assert str(FIXTURES / fixture) in message, "the error does not name the file"


@pytest.mark.adversarial
@pytest.mark.parametrize("fixture", SCHEMA_RULES)
def test_schema_rule_rejects_the_document(fixture: str) -> None:
    document = load_yaml(FIXTURES / fixture / "pack.yaml")
    errors = list(VALIDATOR.iter_errors(document))
    assert errors, f"{fixture} passed schema validation but should not have"


def test_an_unknown_field_is_named_in_the_error() -> None:
    """additionalProperties: false is only useful if it says which property."""
    document = load_yaml(FIXTURES / "unknown-field" / "pack.yaml")
    errors = list(VALIDATOR.iter_errors(document))
    assert any("unexpected_field" in str(error.message) for error in errors)


def test_an_open_ended_core_pin_is_refused() -> None:
    document = load_yaml(FIXTURES / "open-ended-requires-core" / "pack.yaml")
    with pytest.raises(ValueError, match="closed upper bound"):
        parse_range(document["requires_core"])


def test_the_open_ended_pin_is_also_caught_by_the_schema() -> None:
    """Two independent checks, because this one protects reproducibility."""
    document = load_yaml(FIXTURES / "open-ended-requires-core" / "pack.yaml")
    assert list(VALIDATOR.iter_errors(document))


def test_a_pack_error_carries_structured_fields_not_only_a_message() -> None:
    """The CLI formats these; a string would force it to parse its own output."""
    with pytest.raises(PackError) as caught:
        load_yaml(FIXTURES / "duplicate-key" / "pack.yaml")
    error = caught.value
    assert error.path.endswith("pack.yaml")
    assert error.rule
    assert error.location
    assert error.detail


def test_a_missing_file_is_refused_rather_than_treated_as_empty() -> None:
    with pytest.raises(PackError, match="unreadable"):
        load_yaml(FIXTURES / "valid" / "does-not-exist.yaml")


def test_oversized_yaml_is_rejected_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "large.yaml"
    path.write_bytes(b"value: " + b"a" * MAX_YAML_BYTES)

    with pytest.raises(PackError) as caught:
        load_yaml(path)

    assert caught.value.rule == "yaml-byte-limit"


def test_deep_yaml_is_rejected_by_the_parser_budget(tmp_path: Path) -> None:
    path = tmp_path / "deep.yaml"
    path.write_text(
        "value: " + "[" * MAX_YAML_DEPTH + "0" + "]" * MAX_YAML_DEPTH,
        encoding="utf-8",
    )

    with pytest.raises(PackError, match="nesting exceeds"):
        load_yaml(path)


def test_yaml_symlink_is_not_followed(tmp_path: Path) -> None:
    target = tmp_path / "outside.yaml"
    target.write_text("secret: value\n", encoding="utf-8")
    link = tmp_path / "pack.yaml"
    link.symlink_to(target)

    with pytest.raises(PackError) as caught:
        load_yaml(link)

    assert caught.value.rule == "non-regular-file"


def test_yaml_sets_are_rejected_before_they_can_affect_determinism(tmp_path: Path) -> None:
    path = tmp_path / "set.yaml"
    path.write_text("value: !!set {beta: null, alpha: null}\n", encoding="utf-8")

    with pytest.raises(PackError, match="YAML sets are not allowed") as caught:
        load_yaml(path)
    assert caught.value.rule == "strict-yaml"


def test_load_pack_always_enforces_the_running_core_version(tmp_path: Path) -> None:
    pack = tmp_path / "pack"
    shutil.copytree(EXAMPLE_PACK, pack)
    path = pack / "pack.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    document["requires_core"] = ">=9.0,<10.0"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(PackError) as caught:
        load_pack(pack)
    assert caught.value.rule == "core-version-out-of-range"


@pytest.mark.parametrize(
    ("text", "version", "expected"),
    [
        (">=0.1,<0.2", "0.1.0", True),
        (">=0.1,<0.2", "0.1.9", True),
        (">=0.1,<0.2", "0.2.0", False),
        (">=0.1,<0.2", "0.0.9", False),
        (">=1.0.0,<2.0.0", "1.5.3", True),
    ],
)
def test_core_range_membership(text: str, version: str, expected: bool) -> None:
    assert parse_range(text).contains(version) is expected


@pytest.mark.parametrize("bad", [">=0.1", "<0.2", "0.1", ">=0.2,<0.1", "any", ""])
def test_malformed_core_ranges_are_refused(bad: str) -> None:
    with pytest.raises(ValueError, match=r"closed upper bound|empty range"):
        parse_range(bad)
