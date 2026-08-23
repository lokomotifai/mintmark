"""Declarations that used to be read by nothing.

Each test here pins one field that a pack author, a reviewer, or a consuming
script would reasonably take for a control, and which the engine ignored. They
are grouped in one file because they are one defect: a declaration parsed,
schema-checked, and then dropped is worse than an absent one, since the tests
written to guard it guard nothing while looking like they do.
"""

from __future__ import annotations

import collections
import json
import shutil
from pathlib import Path

import pytest

from mintmark.annotate import Label
from mintmark.api import verify
from mintmark.engine.prng import SplitMix64
from mintmark.engine.streams import StreamFactory
from mintmark.identifiers import IdentifierPolicy
from mintmark.manifest import MANIFEST_FILENAME, read_manifest
from mintmark.mint import ENGINE_MAJOR, MintError, _MintContext, mint
from mintmark.packs.loader import PackError
from mintmark.packs.model import load_pack

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "packs" / "example"
CONFORMANCE = REPO_ROOT / "tests" / "conformance" / "pack"


@pytest.fixture
def pack_copy(tmp_path: Path) -> Path:
    destination = tmp_path / "pack"
    shutil.copytree(EXAMPLE, destination)
    return destination


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{path.name} does not contain {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# The recipe decides the identifier policy.


def test_a_recipe_that_names_a_policy_refuses_a_different_one(pack_copy: Path, tmp_path: Path):
    """The defect: nine recipes across the sector packs pinned `safe`, every one
    of those packs asserted it in its own suite, and passing the flag minted
    checksum-valid identifiers anyway."""
    _edit(
        pack_copy / "recipes" / "demo.yaml",
        "special_rate:",
        "identifier_policy: safe\nspecial_rate:",
    )
    with pytest.raises(MintError, match="The recipe decides"):
        mint(
            pack=pack_copy,
            recipe="demo",
            seed=1,
            out=tmp_path / "out",
            identifier_policy="validator",
        )


def test_a_recipe_that_names_a_policy_supplies_it_without_a_flag(pack_copy: Path, tmp_path: Path):
    _edit(
        pack_copy / "recipes" / "demo.yaml",
        "special_rate:",
        "identifier_policy: validator\nspecial_rate:",
    )
    summary = mint(pack=pack_copy, recipe="demo", seed=1, out=tmp_path / "out")
    assert summary.identifier_policy == "validator"


def test_a_recipe_that_names_no_policy_leaves_the_choice_to_the_caller(tmp_path: Path):
    assert mint(pack=EXAMPLE, recipe="demo", seed=1, out=tmp_path / "a").identifier_policy == "safe"
    validator = mint(
        pack=EXAMPLE, recipe="demo", seed=1, out=tmp_path / "b", identifier_policy="validator"
    )
    assert validator.identifier_policy == "validator"


def test_naming_the_same_policy_the_recipe_names_is_allowed(pack_copy: Path, tmp_path: Path):
    """`reproduce` replays what a manifest recorded and cannot know which of the
    two decided it."""
    _edit(
        pack_copy / "recipes" / "demo.yaml",
        "special_rate:",
        "identifier_policy: safe\nspecial_rate:",
    )
    summary = mint(
        pack=pack_copy, recipe="demo", seed=1, out=tmp_path / "out", identifier_policy="safe"
    )
    assert summary.identifier_policy == "safe"


# The sweep runs under both policies.


def test_the_sweep_counts_under_the_validator_policy(tmp_path: Path):
    """The defect: the counter was printed under both policies and filled under
    one, so a validator dataset reported zero checksum-valid identifiers while
    every identifier in it was checksum-valid."""
    out = tmp_path / "validator"
    mint(pack=EXAMPLE, recipe="demo", seed=1, out=out, identifier_policy="validator")
    report = verify(out)
    assert report.checksum_valid_identifiers > 0, "the sweep did not run under validator"
    assert report.ok, "a validator dataset is not a failure, it is a documented mode"
    assert "expected under the validator policy" in report.render()


def test_the_sweep_still_fails_a_safe_dataset_that_carries_a_valid_identifier(tmp_path: Path):
    out = tmp_path / "safe"
    mint(pack=EXAMPLE, recipe="demo", seed=1, out=out)
    path = out / "customer.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    rows[0]["national_id"] = "10000000146"  # checksum-valid TCKN
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", "utf-8")
    report = verify(out)
    assert report.checksum_valid_identifiers >= 1
    assert any("safety claim" in problem for problem in report.problems)


# Template weights.


def test_template_weights_decide_the_draw(tmp_path: Path):
    """The defect: every set was an even mix whatever the pack declared."""
    out = tmp_path / "run"
    mint(pack=EXAMPLE, recipe="demo", seed=9, out=out, records={"transaction": 4000})
    counts: collections.Counter[str] = collections.Counter()
    for line in (out / "transaction.jsonl").read_text(encoding="utf-8").splitlines():
        text = json.loads(line)["description"]
        if "adina" in text:
            counts["transfer_to_person"] += 1  # declared 0.35
        elif "numarali hesaba" in text:
            counts["transfer_to_iban"] += 1  # declared 0.25
        elif "isyerinde" in text:
            counts["card_purchase"] += 1  # declared 0.25
        else:
            counts["bill_payment"] += 1  # declared 0.15
    total = sum(counts.values())
    assert abs(counts["transfer_to_person"] / total - 0.35) < 0.03
    assert abs(counts["bill_payment"] / total - 0.15) < 0.03
    assert counts["transfer_to_person"] > counts["bill_payment"] * 1.8


def test_template_weights_are_scaled_once_per_mint(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import mintmark.mint as mint_module

    calls = 0
    original = mint_module.scale_weights

    def counted(weights: list[str]) -> list[int]:
        nonlocal calls
        calls += 1
        return original(weights)

    monkeypatch.setattr(mint_module, "scale_weights", counted)
    mint(pack=EXAMPLE, recipe="demo", seed=9, out=tmp_path / "run", records={"transaction": 400})

    assert calls == len(load_pack(EXAMPLE).template_sets)


# Coverage targets.


def test_an_unmet_coverage_target_fails_verification(tmp_path: Path):
    """The defect: target, achieved, and a `met` flag were written into every
    manifest and read by nothing."""
    out = tmp_path / "run"
    mint(pack=CONFORMANCE, recipe="full", seed=3, out=out)
    assert verify(out).ok

    document = read_manifest(out)
    assert document["stats"]["coverage_targets"], "the fixture recipe declares targets"
    # Inside the schema's bound on a target, and far above what this mint reached.
    # `met` is corrected at the same time so the only claim under test is the
    # unmet target itself, not the honesty of the flag beside it.
    document["stats"]["coverage_targets"][0]["target"] = 100_000
    document["stats"]["coverage_targets"][0]["met"] = False
    _rewrite_manifest(out, document)

    report = verify(out)
    assert not report.ok
    assert any("was not met" in problem for problem in report.problems)


def test_a_mint_that_overrode_its_record_counts_is_exempt(tmp_path: Path):
    """`packcheck` mini-mints twenty-five records against targets in the
    hundreds. A shrunken run is not a claim the recipe made."""
    out = tmp_path / "small"
    mint(pack=CONFORMANCE, recipe="full", seed=3, out=out, records={"customer": 5})
    report = verify(out)
    assert report.ok
    assert report.coverage_checked is False
    assert "not checked" in report.render()


def _rewrite_manifest(directory: Path, document: dict) -> None:
    """Rewrite a manifest and its checksum lines so only the edit is under test."""
    from mintmark.manifest import SUMS_FILENAME, file_digest, render_sums

    (directory / MANIFEST_FILENAME).write_text(
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False) + "\n", "utf-8"
    )
    sums = {output["path"]: output["sha256"] for output in document["outputs"]}
    sums[MANIFEST_FILENAME] = file_digest(directory / MANIFEST_FILENAME)
    (directory / SUMS_FILENAME).write_text(render_sums(sums), encoding="utf-8")


# Lexicons a pack ships have to be reachable.


def test_a_lexicon_nothing_draws_from_is_refused(pack_copy: Path):
    """The defect: three sector packs shipped eight lexicons, source-noted,
    denylist-tested, and reachable from no generator at all."""
    (pack_copy / "lexicons").mkdir(exist_ok=True)
    (pack_copy / "lexicons" / "orphan.yaml").write_text(
        "name: orphan\nsource_note: invented for this test\nvalues:\n- Bir\n- Iki\n", "utf-8"
    )
    with pytest.raises(PackError, match="unreachable-lexicon"):
        load_pack(pack_copy)


def test_a_template_set_no_field_renders_is_refused(pack_copy: Path):
    target = pack_copy / "templates" / "unused"
    target.mkdir(parents=True)
    (target / "set.yaml").write_text(
        "entries:\n- id: only\n  weight: '1'\n  text: Hicbir alan bunu cizmiyor.\n", "utf-8"
    )
    with pytest.raises(PackError, match="unreachable-template-set"):
        load_pack(pack_copy)


# Entity surfaces a pack contributes.


def test_a_pack_can_add_surfaces_to_an_entity_label(pack_copy: Path, tmp_path: Path):
    """The defect: every pack in the family drew ORG from the same twelve core
    names, so an evaluation set could be passed by memorising them."""
    (pack_copy / "lexicons").mkdir(exist_ok=True)
    (pack_copy / "lexicons" / "employers_fictional.yaml").write_text(
        "name: employers_fictional\nsource_note: invented for this test\nvalues:\n"
        "- Zeytinli Ambalaj\n- Karadut Yazilim\n",
        "utf-8",
    )
    _edit(
        pack_copy / "pack.yaml",
        "dataset_license:",
        "entity_lexicons:\n  ORG: [employers_fictional]\ndataset_license:",
    )
    loaded = load_pack(pack_copy)
    assert loaded.entity_lexicons == {"ORG": ("employers_fictional",)}

    out = tmp_path / "run"
    mint(pack=pack_copy, recipe="demo", seed=4, out=out, records={"transaction": 600})
    surfaces = _org_surfaces(out)
    assert {"Zeytinli Ambalaj", "Karadut Yazilim"} & surfaces, "the pack list never reached a draw"
    assert len(surfaces) > 12, "the core list is a floor, not a replacement"


def test_entity_lexicons_naming_an_undeclared_lexicon_is_refused(pack_copy: Path):
    _edit(
        pack_copy / "pack.yaml",
        "dataset_license:",
        "entity_lexicons:\n  ORG: [nowhere]\ndataset_license:",
    )
    with pytest.raises(PackError, match="unknown-lexicon"):
        load_pack(pack_copy)


def test_entity_lexicon_names_must_be_unique(pack_copy: Path):
    _edit(
        pack_copy / "pack.yaml",
        "dataset_license:",
        "entity_lexicons:\n  ORG: [employers_fictional, employers_fictional]\ndataset_license:",
    )
    with pytest.raises(PackError, match="non-unique elements"):
        load_pack(pack_copy)


def test_entity_surfaces_are_composed_once_per_mint(
    pack_copy: Path, monkeypatch: pytest.MonkeyPatch
):
    (pack_copy / "lexicons").mkdir(exist_ok=True)
    (pack_copy / "lexicons" / "employers_fictional.yaml").write_text(
        "name: employers_fictional\nsource_note: invented for this test\nvalues:\n"
        "- Zeytinli Ambalaj\n- Karadut Yazilim\n",
        "utf-8",
    )
    _edit(
        pack_copy / "pack.yaml",
        "dataset_license:",
        "entity_lexicons:\n  ORG: [employers_fictional]\ndataset_license:",
    )
    loaded = load_pack(pack_copy)
    recipe = loaded.recipe("demo")
    context = _MintContext(
        pack=loaded,
        recipe=recipe,
        factory=StreamFactory(
            seed=1,
            engine_major=ENGINE_MAJOR,
            pack_name=loaded.name,
            pack_version=loaded.version,
            recipe_name=recipe.name,
        ),
        policy=IdentifierPolicy.SAFE,
        counts=dict(recipe.records),
    )
    calls = 0
    original = _MintContext.lexicon_values

    def counted(self: _MintContext, name: str):  # type: ignore[no-untyped-def]
        nonlocal calls
        calls += 1
        return original(self, name)

    monkeypatch.setattr(_MintContext, "lexicon_values", counted)
    for seed in range(100):
        context._descriptor(Label.ORG, SplitMix64(seed))

    assert calls == 1


def _org_surfaces(directory: Path) -> set[str]:
    texts = {
        json.loads(line)["txn_id"]: json.loads(line)["description"]
        for line in (directory / "transaction.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    found: set[str] = set()
    for line in (directory / "transaction.labels.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        text = texts[record["doc_id"]]
        for span in record["spans"]:
            if span["label"] == Label.ORG.value:
                found.add(text[span["start"] : span["end"]])
    return found


# Domain vocabulary a template can vary.


def test_a_lex_slot_renders_a_lexicon_value_without_labelling_it(pack_copy: Path, tmp_path: Path):
    """Domain vocabulary is not personal data, so it carries no span. It exists
    so a template can vary its ordinary words instead of repeating one carrier
    sentence across a whole evaluation set."""
    (pack_copy / "lexicons").mkdir(exist_ok=True)
    (pack_copy / "lexicons" / "perils_tr.yaml").write_text(
        "name: perils_tr\nsource_note: invented for this test\nvalues:\n"
        "- cam kirilmasi\n- su basmasi\n",
        "utf-8",
    )
    _edit(
        pack_copy / "templates" / "txn_descriptions" / "set.yaml",
        "Fatura odemesi (tamamlandi|gerceklesti)",
        "Fatura odemesi {lex:perils_tr} (tamamlandi|gerceklesti)",
    )
    out = tmp_path / "run"
    mint(pack=pack_copy, recipe="demo", seed=5, out=out, records={"transaction": 400})
    text = (out / "transaction.jsonl").read_text(encoding="utf-8")
    assert "cam kirilmasi" in text or "su basmasi" in text

    labelled = _org_surfaces(out)
    assert not ({"cam kirilmasi", "su basmasi"} & labelled), "domain vocabulary took a label"


def test_a_lex_slot_naming_nothing_the_pack_declares_is_refused(pack_copy: Path, tmp_path: Path):
    _edit(
        pack_copy / "templates" / "txn_descriptions" / "set.yaml",
        "Fatura odemesi",
        "Fatura odemesi {lex:hicbiryerde}",
    )
    with pytest.raises(Exception, match="unknown-lexicon"):
        mint(pack=pack_copy, recipe="demo", seed=5, out=tmp_path / "run")
