"""Pack-controlled numeric work must fit the core's finite sampler domain."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import jsonschema
import pytest
import yaml

from mintmark.engine.draws import TWO64
from mintmark.minting import MintError, mint
from mintmark.packs.model import MAX_RECORDS_PER_TYPE, PackError, load_pack

CONFORMANCE = Path(__file__).resolve().parents[1] / "conformance" / "pack"


def _copy_pack(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(CONFORMANCE, target)
    return target


def _rewrite(path: Path, mutate) -> None:  # type: ignore[no-untyped-def]
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(yaml.safe_dump(document, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_int_uniform_wider_than_u64_is_rejected_during_pack_load(tmp_path: Path) -> None:
    pack = _copy_pack(tmp_path, "wide-range")
    path = pack / "fields" / "customer.yaml"

    def widen(document: dict[str, object]) -> None:
        field = next(item for item in document["fields"] if item["name"] == "vehicle_year")  # type: ignore[index, union-attr]
        field["params"] = {"low": 0, "high": TWO64}  # type: ignore[index]

    _rewrite(path, widen)

    with pytest.raises(PackError) as caught:
        load_pack(pack)
    assert caught.value.rule == "sampler-domain-limit"


def test_overprecise_probability_is_rejected_during_pack_load(tmp_path: Path) -> None:
    pack = _copy_pack(tmp_path, "precise-rate")
    path = pack / "fields" / "transaction.yaml"

    def overprecision(document: dict[str, object]) -> None:
        field = next(
            item
            for item in document["fields"]
            if item["name"] == "counterparty_iban"  # type: ignore[index, union-attr]
        )
        field["null_rate"] = "0.00000000000000000001"  # type: ignore[index]

    _rewrite(path, overprecision)

    with pytest.raises(PackError) as caught:
        load_pack(pack)
    assert caught.value.rule == "decimal-precision-limit"


def test_scaled_weight_total_above_u64_is_rejected_during_pack_load(tmp_path: Path) -> None:
    pack = _copy_pack(tmp_path, "huge-weights")
    path = pack / "fields" / "customer.yaml"

    def enlarge(document: dict[str, object]) -> None:
        field = next(item for item in document["fields"] if item["name"] == "segment")  # type: ignore[index, union-attr]
        field["params"]["weights"] = [str(TWO64), "1", "1"]  # type: ignore[index]

    _rewrite(path, enlarge)

    with pytest.raises(PackError) as caught:
        load_pack(pack)
    assert caught.value.rule == "sampler-domain-limit"


def test_existing_conformance_pack_stays_valid() -> None:
    loaded = load_pack(CONFORMANCE)
    assert loaded.recipe("full").records["transaction"] == 120
    assert loaded.lexicons["ratings"] == ("0.25", "0.50", "0.75", "1.00")


def test_recipe_record_count_is_bounded(tmp_path: Path) -> None:
    pack = _copy_pack(tmp_path, "huge-recipe")
    path = pack / "recipes" / "full.yaml"

    def enlarge(document: dict[str, object]) -> None:
        document["records"]["transaction"] = MAX_RECORDS_PER_TYPE + 1  # type: ignore[index]

    _rewrite(path, enlarge)

    with pytest.raises(PackError):
        load_pack(pack)


def test_manifest_schema_uses_the_pack_record_count_budget(tmp_path: Path) -> None:
    out = tmp_path / "manifest-budget"
    mint(pack=CONFORMANCE, recipe="full", seed=1, out=out, invocation="pytest")
    document = json.loads((out / "MINTMARK.json").read_text(encoding="utf-8"))
    schema = json.loads(
        (Path(__file__).resolve().parents[2] / "schemas" / "manifest.schema.json").read_text(
            encoding="utf-8"
        )
    )

    document["recipe"]["parameters"]["records"]["transaction"] = MAX_RECORDS_PER_TYPE
    document["stats"]["record_counts"]["transaction"] = MAX_RECORDS_PER_TYPE
    jsonschema.validate(document, schema)

    document["recipe"]["parameters"]["records"]["transaction"] = MAX_RECORDS_PER_TYPE + 1
    document["stats"]["record_counts"]["transaction"] = MAX_RECORDS_PER_TYPE + 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, schema)


def test_runtime_record_override_uses_the_same_budget(tmp_path: Path) -> None:
    out = tmp_path / "out"
    with pytest.raises(MintError, match="record-count-limit"):
        mint(
            pack=CONFORMANCE,
            recipe="full",
            seed=1,
            out=out,
            records={"customer": MAX_RECORDS_PER_TYPE + 1},
            invocation="pytest",
        )
    assert not out.exists()


def test_generated_output_bytes_are_bounded_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mintmark.minting as mint_module

    monkeypatch.setattr(mint_module, "MAX_DATA_FILE_BYTES", 512)
    out = tmp_path / "out"
    with pytest.raises(MintError, match="output-byte-limit"):
        mint(pack=CONFORMANCE, recipe="full", seed=1, out=out, invocation="pytest")
    assert not out.exists()


def test_pack_lexicon_rejects_structured_values_instead_of_stringifying_them(
    tmp_path: Path,
) -> None:
    pack = _copy_pack(tmp_path, "structured-lexicon")
    path = pack / "lexicons" / "ratings.yaml"

    def structure(document: dict[str, object]) -> None:
        document["values"] = [{"secret": "value"}]

    _rewrite(path, structure)

    with pytest.raises(PackError) as caught:
        load_pack(pack)
    assert caught.value.rule == "lexicon-value-type"


def test_duplicate_record_type_name_is_rejected(tmp_path: Path) -> None:
    pack = _copy_pack(tmp_path, "duplicate-type")
    shutil.copy2(pack / "fields" / "customer.yaml", pack / "fields" / "duplicate.yaml")

    with pytest.raises(PackError) as caught:
        load_pack(pack)
    assert caught.value.rule == "duplicate-record-type"


def test_hidden_yaml_does_not_change_loaded_declarations_or_digest(tmp_path: Path) -> None:
    pack = _copy_pack(tmp_path, "hidden-declaration")
    before = load_pack(pack)
    shutil.copy2(pack / "fields" / "customer.yaml", pack / "fields" / ".shadow.yaml")

    after = load_pack(pack)

    assert after.digest == before.digest
    assert [item.type_name for item in after.record_types] == [
        item.type_name for item in before.record_types
    ]
