"""Independent semantic boundaries for special-category descriptor data."""

from pathlib import Path

import yaml

DESCRIPTORS = (
    Path(__file__).resolve().parents[2] / "src/mintmark/lexicons/data/special_descriptors.yaml"
)


def test_special_descriptors_stay_inside_their_declared_categories() -> None:
    labels = yaml.safe_load(DESCRIPTORS.read_text(encoding="utf-8"))["labels"]

    health_forbidden = {
        "ameliyat",
        "cerrahi",
        "tedavi",
        "terapi",
        "ilaç",
        "muayene",
        "randevu",
        "sevk",
        "protokol",
    }
    ethnicity_forbidden = {"dil", "tercüman", "çeviri", "yazışma", "iletişim"}
    sexual_life_forbidden = {"medeni", "aile", "nikah", "boşan", "gebelik"}

    def offenders(label: str, forbidden: set[str]) -> list[str]:
        return [
            value
            for value in labels[label]["values"]
            if any(term in value.casefold() for term in forbidden)
        ]

    assert not offenders("HEALTH", health_forbidden)
    assert not offenders("ETHNICITY", ethnicity_forbidden)
    assert not offenders("SEXUAL_LIFE", sexual_life_forbidden)
    assert all(
        "cinsel" in value.casefold() or "mahrem" in value.casefold()
        for value in labels["SEXUAL_LIFE"]["values"]
    )
