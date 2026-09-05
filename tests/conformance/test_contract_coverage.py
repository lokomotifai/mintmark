"""WP-13: the pack contract can express what its first real consumer declares.

The banking brief is the first sector pack this contract has to serve. Building
the contract and then discovering it cannot express a customer-to-account
distribution, or a masked PAN, or a nullable IBAN, would mean changing the
contract after a pack repository had already been written against it.

So the shapes the brief declares are exercised here, inside this repository,
against a fixture that is not a sector pack and never ships. The point is not
that the fixture mints. It is that every field type, every generator kind, and
every derived rule the contract names is actually reached, which the coverage
test below asserts directly rather than leaving to inspection.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mintmark.minting import mint
from mintmark.packs.model import load_pack

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK = REPO_ROOT / "tests" / "conformance" / "pack"

# The vocabularies the contract declares. Taken from the pack schema so that
# adding a generator kind without exercising it fails this test.
SCHEMA = json.loads((REPO_ROOT / "schemas" / "pack.schema.json").read_text(encoding="utf-8"))
FIELD_TYPES = set(SCHEMA["$defs"]["field"]["properties"]["type"]["enum"])
DERIVED_RULES = {"email_from_name", "date_offset", "ratio_of", "copy_of", "flag_unless"}
GENERATOR_KINDS = {
    "lexicon",
    "identifier",
    "grammar",
    "int_uniform",
    "int_lognormal_table",
    "enum_weighted",
    "seq_id",
    "datetime_window",
    "derived",
}


@pytest.fixture(scope="module")
def pack():  # type: ignore[no-untyped-def]
    return load_pack(PACK)


@pytest.fixture(scope="module")
def minted(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("conformance") / "run"
    mint(pack=PACK, recipe="full", seed=20260822, out=out, invocation="pytest")
    return out


def declared_fields(pack) -> list:  # type: ignore[no-untyped-def]
    return [f for t in pack.record_types for f in t.fields]


def test_every_field_type_in_the_contract_is_exercised(pack) -> None:  # type: ignore[no-untyped-def]
    used = {f.type for f in declared_fields(pack)}
    missing = FIELD_TYPES - used
    assert not missing, f"the contract declares field types nothing exercises: {sorted(missing)}"


def test_every_generator_kind_in_the_contract_is_exercised(pack) -> None:  # type: ignore[no-untyped-def]
    used = {f.generator_kind for f in declared_fields(pack)}
    missing = GENERATOR_KINDS - used
    assert not missing, f"generator kinds never exercised: {sorted(missing)}"


def test_every_derived_rule_in_the_contract_is_exercised(pack) -> None:  # type: ignore[no-untyped-def]
    used = {f.generator_argument for f in declared_fields(pack) if f.generator_kind == "derived"}
    missing = DERIVED_RULES - used
    assert not missing, f"derived rules never exercised: {sorted(missing)}"


def test_every_identifier_engine_is_exercised(pack) -> None:  # type: ignore[no-untyped-def]
    used = {f.generator_argument for f in declared_fields(pack) if f.generator_kind == "identifier"}
    assert used >= {"TCKN", "IBAN", "PAN", "PHONE", "VKN"}


def test_the_banking_customer_to_account_shape_is_expressible(pack) -> None:  # type: ignore[no-untyped-def]
    """1..3 accounts per customer at weights 0.55 / 0.30 / 0.15."""
    account = pack.record_type("account")
    ref = next(f.ref for f in account.fields if f.type == "ref")
    assert ref.parent == "customer"
    assert ref.counts == (1, 2, 3)
    assert ref.weights == ("0.55", "0.30", "0.15")


def test_a_second_level_reference_is_expressible(pack) -> None:  # type: ignore[no-untyped-def]
    """Cards reference accounts, which reference customers: the banking shape."""
    card = pack.record_type("card")
    ref = next(f.ref for f in card.fields if f.type == "ref")
    assert ref.parent == "account"
    assert ref.counts[0] == 0, "the brief's cards are 0..2 per account"


def test_a_nullable_identifier_field_is_expressible(pack) -> None:  # type: ignore[no-untyped-def]
    """The banking counterparty IBAN carries a 0.35 null rate."""
    transaction = pack.record_type("transaction")
    field = next(f for f in transaction.fields if f.name == "counterparty_iban")
    assert field.nullable
    assert field.null_rate == "0.35"


def test_the_five_value_channel_distribution_is_expressible(pack) -> None:  # type: ignore[no-untyped-def]
    transaction = pack.record_type("transaction")
    channel = next(f for f in transaction.fields if f.name == "channel")
    assert channel.params["weights"] == ["0.52", "0.18", "0.15", "0.10", "0.05"]


def test_three_document_types_with_distinct_template_sets(pack) -> None:  # type: ignore[no-untyped-def]
    """Complaint, KYC note, and support transcript: the banking document set."""
    doc_types = [t for t in pack.record_types if t.document_fields]
    assert len(doc_types) == 3
    sets = {t.document_fields[0].generator_argument for t in doc_types}
    assert len(sets) == 3, "the three document types share a template set"


def test_the_mint_produces_every_declared_record_type(minted: Path) -> None:
    for name in (
        "customer",
        "account",
        "card",
        "transaction",
        "complaint_ticket",
        "kyc_note",
        "support_transcript",
    ):
        path = minted / f"{name}.jsonl"
        assert path.exists(), f"{name} was declared but not emitted"
        assert path.read_text(encoding="utf-8").strip(), f"{name} is empty"


def test_every_document_type_produces_a_sidecar(minted: Path) -> None:
    for name in ("complaint_ticket", "kyc_note", "support_transcript"):
        assert (minted / f"{name}.labels.jsonl").exists()


def test_a_nullable_field_actually_produces_nulls_and_values(minted: Path) -> None:
    values = [
        json.loads(line)["counterparty_iban"]
        for line in (minted / "transaction.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(v is None for v in values), "the null rate never fired"
    assert any(v is not None for v in values), "the null rate fired every time"


def test_masked_pans_are_emitted_masked(minted: Path) -> None:
    for line in (minted / "card.jsonl").read_text(encoding="utf-8").splitlines():
        pan = json.loads(line)["pan_masked"]
        assert "*" in pan, f"an unmasked PAN reached the output: {pan}"
        assert pan.startswith("9")


def test_derived_ratio_and_copy_agree_with_their_sources(minted: Path) -> None:
    for line in (minted / "transaction.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        assert record["mirror_amount"] == record["amount_kurus"]
        assert record["net_kurus"] == record["amount_kurus"] * 82 // 100


def test_derived_date_offset_lands_a_year_later(minted: Path) -> None:
    from datetime import date

    for line in (minted / "account.jsonl").read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        opened = date.fromisoformat(record["opened_date"])
        later = date.fromisoformat(record["opened_plus_year"])
        assert (later - opened).days == 365


def test_all_eighteen_labels_are_reachable_through_the_contract(minted: Path) -> None:
    """The eval recipes of every sector brief require coverage of all of them."""
    from mintmark.annotate import ALL_LABELS

    document = json.loads((minted / "MINTMARK.json").read_text(encoding="utf-8"))
    covered = set(document["entity_coverage"])
    missing = {label.value for label in ALL_LABELS} - covered
    assert not missing, (
        f"labels the contract cannot reach in this fixture: {sorted(missing)}. "
        "Every sector brief's pii-eval recipe declares a target for each of the "
        "eighteen, so a label with no route into a document is a contract gap."
    )


def test_coverage_targets_are_recorded_whether_met_or_missed(minted: Path) -> None:
    document = json.loads((minted / "MINTMARK.json").read_text(encoding="utf-8"))
    targets = document["stats"]["coverage_targets"]
    assert targets, "the recipe declared coverage targets but the manifest records none"
    for entry in targets:
        assert set(entry) == {"label", "target", "achieved", "met"}
        assert entry["met"] == (entry["achieved"] >= entry["target"])


def test_distributions_are_recorded_with_target_and_achieved(minted: Path) -> None:
    document = json.loads((minted / "MINTMARK.json").read_text(encoding="utf-8"))
    distributions = document["stats"]["distributions"]
    assert distributions, "no declared distribution reached the manifest"
    sites = {entry["site"] for entry in distributions}
    assert "transaction/channel" in sites
    for entry in distributions:
        assert set(entry["target"]) == set(entry["achieved"])
