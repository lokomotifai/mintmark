"""Invariant 7: no real institution name reaches generated content.

The denylist is a brand and legal control, so it is tested in both directions. It
must catch a real institution planted in a lexicon, and it must not fire on the
ordinary Turkish words that several real institutions happen to be named after.

The second half is not politeness toward false positives. A lint that flags
"hayat" in a sentence about life insurance gets switched off within a week, and a
control that has been switched off protects nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mintmark.lexicons import Denylist, load, parse

REPO_ROOT = Path(__file__).resolve().parents[2]
DENYLIST_PATH = REPO_ROOT / "assets" / "denylist" / "institutions-tr.txt"
LEXICON_DIR = REPO_ROOT / "src" / "mintmark" / "lexicons" / "data"

CORE = load(DENYLIST_PATH)


def test_the_denylist_is_populated_from_the_verified_source() -> None:
    assert len(CORE) >= 60, f"only {len(CORE)} entries; the TCMB list carries 71 participants"
    text = DENYLIST_PATH.read_text(encoding="utf-8")
    assert "TCMB" in text
    assert "2026-08-22" in text, "the denylist carries no retrieval date"


@pytest.mark.parametrize(
    "institution",
    [
        "Akbank T.A.Ş.",
        "DENİZBANK A.Ş.",
        "Yapı ve Kredi Bankası A.Ş.",
        "garanti bankasi",
        "QNB Finansbank",
        "Kuveyt Türk Katılım Bankası",
    ],
)
def test_a_real_institution_is_caught(institution: str) -> None:
    hits = CORE.scan(institution)
    assert hits, f"{institution!r} passed the denylist unnoticed"
    assert hits[0].entry
    assert hits[0].source


def test_a_hit_names_both_sides_of_the_collision() -> None:
    """A failure that does not say what it collided with cannot be acted on."""
    hit = CORE.scan("Akbank Sigorta")[0]
    rendered = hit.render()
    assert "Akbank Sigorta" in rendered
    assert "akbank" in rendered.lower()
    assert "real institution" in rendered


@pytest.mark.parametrize(
    "fictional",
    ["Anka Bank", "Meridyen Bank", "Toros Katılım", "Anka Sigorta", "Meridyen Teknoloji"],
)
def test_the_demonstrated_fictional_names_pass(fictional: str) -> None:
    assert not CORE.scan(fictional), f"{fictional!r} collided with a real institution"


@pytest.mark.parametrize(
    "sentence",
    [
        "Hayat sigortası poliçesi yenilendi.",
        "Dünya genelinde bir uygulama.",
        "Hedef tutarına ulaşıldı.",
        "Destek talebi oluşturuldu.",
        "Aktif hesap sayısı arttı.",
        "Adil bir çözüm bulundu.",
        "Merkez şubeye başvuruldu.",
        "Ticaret hacmi büyüdü.",
        "Ekonomi haberleri okundu.",
        "Vakıf üyeliği devam ediyor.",
    ],
)
def test_ordinary_turkish_prose_does_not_trip_the_scan(sentence: str) -> None:
    """Several real banks are named after ordinary nouns; the words stay usable."""
    hits = CORE.scan(sentence)
    assert not hits, f"false positive on ordinary prose: {[h.entry for h in hits]}"


def test_matching_is_word_boundary_aware_not_substring() -> None:
    """'ing' is a bank. It is also inside a great many Turkish and English words."""
    assert CORE.scan("ING Bank hesabı")
    assert not CORE.scan("Brifing notu hazırlandı.")
    assert not CORE.scan("Leasing sözleşmesi imzalandı.")


def test_matching_folds_turkish_characters() -> None:
    """A hit carries the surface it was found in, so compare the entries matched."""
    upper = [hit.entry for hit in CORE.scan("ŞEKERBANK")]
    folded = [hit.entry for hit in CORE.scan("sekerbank")]
    assert upper == folded != []
    assert CORE.scan("Türkiye İş Bankası")


@pytest.mark.parametrize(
    "institution",
    [
        "Türkiye İş Bankası A.Ş.",
        "T. İŞ BANKASI A.Ş.",
        "Yapı ve Kredi Bankası",
        "Şekerbank T.A.Ş.",
        "Hayat Finans Katılım Bankası",
        "Dünya Katılım Bankası",
    ],
)
def test_institutions_whose_brand_is_short_or_generic_are_still_caught(
    institution: str,
) -> None:
    """The gap this test was written for: 'is' is two characters and also a word.

    Stripping legal-form and category words from "T. IS BANKASI A.S." leaves
    "is", which fell below the minimum entry length and took one of the
    country's largest banks off the list entirely. Short and generic cores are
    now qualified rather than dropped.
    """
    assert CORE.scan(institution), f"{institution!r} is not covered by the denylist"


def test_every_participant_in_the_source_list_is_covered() -> None:
    """No institution may drop out of the list during extraction."""
    text = DENYLIST_PATH.read_text(encoding="utf-8")
    sources = [
        line.split("#", 1)[1].strip()
        for line in text.splitlines()
        if "#" in line and not line.strip().startswith("#")
    ]
    assert len(sources) >= 70, f"only {len(sources)} institutions carried through"
    uncovered = [name for name in sources if not CORE.scan(name)]
    assert not uncovered, f"listed but unmatchable: {uncovered}"


def test_every_shipped_lexicon_value_passes_the_scan() -> None:
    """The names this project actually emits, checked against the real list."""
    offenders: list[str] = []
    for path in sorted(LEXICON_DIR.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        for value in _iter_strings(payload):
            for hit in CORE.scan(value):
                offenders.append(f"{path.name}: {hit.render()}")
    assert not offenders, "\n".join(offenders)


def test_every_factual_lexicon_carries_a_source_note_with_a_date() -> None:
    """Section 7.3 of the repository standard, asserted rather than trusted."""
    for path in sorted(LEXICON_DIR.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "source_note" in payload, f"{path.name} carries no source note"
        assert len(payload["source_note"]) > 40, f"{path.name} has a token source note"

    provinces = yaml.safe_load((LEXICON_DIR / "provinces_tr.yaml").read_text(encoding="utf-8"))
    assert "2026-08-22" in provinces["source_note"], "factual data with no retrieval date"


def test_province_plate_codes_cover_the_full_range() -> None:
    provinces = yaml.safe_load((LEXICON_DIR / "provinces_tr.yaml").read_text(encoding="utf-8"))
    codes = [int(entry["plate"]) for entry in provinces["values"]]
    assert codes == list(range(1, 82)), "plate codes are not a complete 1..81 run"


def test_an_empty_denylist_is_refused() -> None:
    """An empty list permits everything while looking like a control."""
    with pytest.raises(ValueError, match="empty denylist"):
        parse("# only comments\n\n")


def test_a_too_short_entry_is_refused() -> None:
    with pytest.raises(ValueError, match="shorter than three characters"):
        parse("ab    # something\n")


def test_a_pack_denylist_must_cover_the_core_one() -> None:
    """Packs may extend the list and may never shrink it."""
    extended = parse(DENYLIST_PATH.read_text(encoding="utf-8") + "\nturkiye sigorta   # TSB\n")
    assert extended.covers(CORE)
    assert not CORE.covers(extended)
    assert CORE.missing_from(extended) == {"turkiye sigorta"}


def test_a_shrunken_pack_denylist_is_detected() -> None:
    shrunken = Denylist(entries=dict(list(CORE.entries.items())[:5]))
    assert not shrunken.covers(CORE)
    assert len(shrunken.missing_from(CORE)) == len(CORE) - 5


def _iter_strings(payload: object) -> list[str]:
    if isinstance(payload, str):
        return [payload]
    if isinstance(payload, list):
        return [s for item in payload for s in _iter_strings(item)]
    if isinstance(payload, dict):
        return [
            s
            for key, value in payload.items()
            if key not in {"source_note", "name"}
            for s in _iter_strings(value)
        ]
    return []
