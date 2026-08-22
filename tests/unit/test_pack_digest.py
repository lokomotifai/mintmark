"""The pack digest is stable, content-sensitive, and blind to committed output.

A manifest records which pack produced a dataset. A name and version cannot carry
that: two builds of one version can differ. The digest is what lets a consumer
holding published artifacts confirm they have the declarations that minted them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mintmark.packs.digest import canonical_lines, enumerate_files, pack_digest

CONFORMANCE = Path(__file__).resolve().parents[1] / "conformance" / "pack"


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


# What the digest covers, and the three ways the old boundary failed.


def test_the_digest_is_the_same_from_a_clean_clone_and_a_working_checkout(
    tmp_path: Path,
) -> None:
    """It used to depend on files a clone does not have.

    A working checkout carries untracked things a clean clone does not: compiled
    caches, a local plan file, a built virtual environment. When the digest
    covered the whole directory, two people on the same commit computed different
    digests, and neither matched the one a published dataset recorded.
    """
    import shutil

    from mintmark.packs.digest import pack_digest

    clean = tmp_path / "clean"
    shutil.copytree(CONFORMANCE, clean)
    working = tmp_path / "working"
    shutil.copytree(CONFORMANCE, working)

    (working / "PLAN.md").write_text("a local file kept out of git\n", encoding="utf-8")
    (working / "NOTES.txt").write_text("scratch\n", encoding="utf-8")
    cache = working / "tests" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "test_thing.cpython-312.pyc").write_bytes(b"\x00compiled\x00")
    (working / "uv.lock").write_text("version = 1\n", encoding="utf-8")

    assert pack_digest(clean) == pack_digest(working), (
        "untracked and generated files still reach the digest"
    )


def test_documentation_does_not_move_the_digest(tmp_path: Path) -> None:
    """A README edit is not a change to what a pack emits."""
    import shutil

    from mintmark.packs.digest import pack_digest

    pack = tmp_path / "pack"
    shutil.copytree(CONFORMANCE, pack)
    before = pack_digest(pack)
    (pack / "README.md").write_text("# Rewritten\n\nEntirely different prose.\n", encoding="utf-8")
    (pack / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    assert pack_digest(pack) == before


def test_a_declaration_does_move_the_digest(tmp_path: Path) -> None:
    """Narrowing the boundary must not have narrowed it into uselessness."""
    import shutil

    from mintmark.packs.digest import pack_digest

    pack = tmp_path / "pack"
    shutil.copytree(CONFORMANCE, pack)
    before = pack_digest(pack)

    manifest = pack / "pack.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("version: 0.1.0", "version: 0.2.0"),
        encoding="utf-8",
    )
    assert pack_digest(pack) != before, "a pack.yaml change did not move the digest"

    shutil.rmtree(pack)
    shutil.copytree(CONFORMANCE, pack)
    template = next((pack / "templates").rglob("*.yaml"))
    template.write_text(template.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert pack_digest(pack) != before, "a template change did not move the digest"


def test_every_directory_the_loader_reads_is_inside_the_digest() -> None:
    """The allowlist and the loader must not drift apart.

    If the loader learns to read a new directory and this list does not, a pack
    could change what it emits without changing its digest, which is the failure
    the digest exists to make impossible.
    """
    from mintmark.packs.digest import DECLARATIVE_DIRECTORIES, DECLARATIVE_FILES

    assert "pack.yaml" in DECLARATIVE_FILES
    assert {"fields", "recipes", "templates", "lexicons"} <= DECLARATIVE_DIRECTORIES
