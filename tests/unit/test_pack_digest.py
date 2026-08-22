"""The pack digest is stable, content-sensitive, and blind to committed output.

A manifest records which pack produced a dataset. A name and version cannot carry
that: two builds of one version can differ. The digest is what lets a consumer
holding published artifacts confirm they have the declarations that minted them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mintmark.packs.digest import canonical_lines, enumerate_files, pack_digest


@pytest.fixture
def pack(tmp_path: Path) -> Path:
    root = tmp_path / "pack"
    (root / "fields").mkdir(parents=True)
    (root / "recipes").mkdir()
    (root / "pack.yaml").write_text("name: mintmark-fixture\n", encoding="utf-8")
    (root / "fields" / "customer.yaml").write_text("type_name: customer\n", encoding="utf-8")
    (root / "recipes" / "demo.yaml").write_text("name: demo\n", encoding="utf-8")
    return root


def test_digest_is_reproducible(pack: Path) -> None:
    assert pack_digest(pack) == pack_digest(pack)
    assert len(pack_digest(pack)) == 64


def test_digest_changes_when_any_covered_file_changes(pack: Path) -> None:
    before = pack_digest(pack)
    (pack / "fields" / "customer.yaml").write_text("type_name: musteri\n", encoding="utf-8")
    assert pack_digest(pack) != before


def test_digest_changes_when_a_file_is_added(pack: Path) -> None:
    before = pack_digest(pack)
    (pack / "recipes" / "second.yaml").write_text("name: second\n", encoding="utf-8")
    assert pack_digest(pack) != before


def test_digest_changes_when_a_file_is_renamed(pack: Path) -> None:
    """The path is hashed alongside the content, so a move is a change."""
    before = pack_digest(pack)
    (pack / "recipes" / "demo.yaml").rename(pack / "recipes" / "demo2.yaml")
    assert pack_digest(pack) != before


def test_digest_ignores_committed_samples(pack: Path) -> None:
    """Otherwise refreshing samples would change the digest of its own input."""
    before = pack_digest(pack)
    samples = pack / "samples"
    samples.mkdir()
    (samples / "customer.jsonl").write_text('{"a":1}\n', encoding="utf-8")
    assert pack_digest(pack) == before

    (samples / "customer.jsonl").write_text('{"a":2}\n', encoding="utf-8")
    assert pack_digest(pack) == before


def test_digest_ignores_datasets(pack: Path) -> None:
    before = pack_digest(pack)
    datasets = pack / "datasets"
    datasets.mkdir()
    (datasets / "big.jsonl").write_text("x" * 1000, encoding="utf-8")
    assert pack_digest(pack) == before


def test_digest_ignores_dot_directories_and_os_droppings(pack: Path) -> None:
    """A contributor's editor or operating system must not change the digest."""
    before = pack_digest(pack)
    (pack / ".git").mkdir()
    (pack / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (pack / ".DS_Store").write_bytes(b"\x00\x01")
    assert pack_digest(pack) == before


def test_enumeration_is_sorted_bytewise_by_posix_path(pack: Path) -> None:
    (pack / "fields" / "Zebra.yaml").write_text("a: 1\n", encoding="utf-8")
    (pack / "fields" / "apple.yaml").write_text("a: 1\n", encoding="utf-8")
    relative = [p.relative_to(pack).as_posix() for p in enumerate_files(pack)]
    assert relative == sorted(relative), "enumeration is not bytewise sorted"
    # Bytewise, not case-insensitive: uppercase sorts before lowercase.
    assert relative.index("fields/Zebra.yaml") < relative.index("fields/apple.yaml")


def test_canonical_lines_have_the_documented_shape(pack: Path) -> None:
    raw = canonical_lines(pack)
    lines = raw.split(b"\x0a")[:-1]
    assert len(lines) == 3
    for line in lines:
        path_part, _, digest_part = line.partition(b"\x00")
        assert path_part
        assert len(digest_part) == 64
        assert digest_part == digest_part.lower()


def test_a_non_directory_is_refused() -> None:
    with pytest.raises(NotADirectoryError):
        pack_digest(Path(__file__))


def test_two_packs_with_identical_content_share_a_digest(tmp_path: Path) -> None:
    """The digest describes declarations, not where they happen to live."""
    for name in ("a", "b"):
        root = tmp_path / name
        root.mkdir()
        (root / "pack.yaml").write_text("name: mintmark-fixture\n", encoding="utf-8")
    assert pack_digest(tmp_path / "a") == pack_digest(tmp_path / "b")
