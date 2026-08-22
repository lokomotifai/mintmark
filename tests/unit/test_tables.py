"""Tables load only when they match their checksum, and sampling stays integral."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mintmark.engine.prng import SplitMix64
from mintmark.engine.tables import SUBDIVISIONS, Table, TableError, load_table, sample

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLE_DIR = REPO_ROOT / "assets" / "tables"
TABLE_NAMES = ["balances", "txn_amounts"]


@pytest.mark.parametrize("name", TABLE_NAMES)
def test_committed_table_loads_and_verifies(name: str) -> None:
    table = load_table(TABLE_DIR, name)
    assert len(table.values) == 1024
    assert table.unit == "kurus"


@pytest.mark.parametrize("name", TABLE_NAMES)
def test_committed_table_is_monotonic(name: str) -> None:
    values = load_table(TABLE_DIR, name).values
    assert all(values[i] <= values[i + 1] for i in range(len(values) - 1))


def test_generator_reproduces_the_committed_tables() -> None:
    """The committed tables were produced by the script, not edited by hand."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "gen_tables.py"), "--verify"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_altered_table_is_refused_rather_than_sampled(tmp_path: Path) -> None:
    """A checksum mismatch must refuse the load, not warn and continue."""
    for name in TABLE_NAMES:
        (tmp_path / f"{name}.json").write_text(
            (TABLE_DIR / f"{name}.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
    (tmp_path / "CHECKSUMS").write_text(
        (TABLE_DIR / "CHECKSUMS").read_text(encoding="utf-8"), encoding="utf-8"
    )

    payload = json.loads((tmp_path / "balances.json").read_text(encoding="utf-8"))
    payload["values"][10] += 1
    (tmp_path / "balances.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(TableError, match="does not match its recorded checksum"):
        load_table(tmp_path, "balances")


def test_missing_checksums_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / "balances.json").write_text('{"unit":"kurus","values":[1,2]}', encoding="utf-8")
    with pytest.raises(TableError, match="no CHECKSUMS file"):
        load_table(tmp_path, "balances")


def test_unknown_table_names_the_correct_remedy(tmp_path: Path) -> None:
    (tmp_path / "CHECKSUMS").write_text("", encoding="utf-8")
    with pytest.raises(TableError, match="core change rather than a pack workaround"):
        load_table(tmp_path, "premiums")


def test_non_monotonic_table_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match="not monotonic"):
        Table(name="broken", unit="kurus", values=(1, 5, 3), digest="x")


def test_single_knot_table_is_refused() -> None:
    with pytest.raises(ValueError, match="at least two knots"):
        Table(name="tiny", unit="kurus", values=(1,), digest="x")


def test_samples_stay_within_the_table_support() -> None:
    table = load_table(TABLE_DIR, "txn_amounts")
    stream = SplitMix64(20260822)
    for _ in range(5000):
        value = sample(stream, table)
        assert table.minimum <= value <= table.maximum


def test_samples_are_integers_not_floats() -> None:
    """A float here would put the emitted bytes at the mercy of rounding."""
    table = load_table(TABLE_DIR, "balances")
    stream = SplitMix64(1)
    for _ in range(256):
        assert type(sample(stream, table)) is int


def test_sampling_is_reproducible_from_the_same_seed() -> None:
    table = load_table(TABLE_DIR, "balances")
    first = [sample(SplitMix64(77), table) for _ in range(1)]
    second = [sample(SplitMix64(77), table) for _ in range(1)]
    assert first == second

    a, b = SplitMix64(99), SplitMix64(99)
    assert [sample(a, table) for _ in range(64)] == [sample(b, table) for _ in range(64)]


def test_interpolation_reaches_inside_a_knot_interval() -> None:
    """Without the second draw the sampler would emit only the 1024 knots."""
    table = Table(name="linear", unit="kurus", values=tuple(range(0, 10240, 10)), digest="x")
    stream = SplitMix64(4242)
    values = {sample(stream, table) for _ in range(4000)}
    off_knot = {v for v in values if v % 10 != 0}
    assert off_knot, "every sample landed exactly on a knot; interpolation is not happening"


def test_flat_interval_interpolates_to_its_single_value() -> None:
    table = Table(name="flat", unit="kurus", values=(500, 500, 500), digest="x")
    stream = SplitMix64(11)
    assert {sample(stream, table) for _ in range(200)} == {500}


def test_subdivision_resolution_is_a_power_of_two() -> None:
    """Keeps the position draw's rejection window trivially wide."""
    assert SUBDIVISIONS & (SUBDIVISIONS - 1) == 0


def test_median_of_the_balances_table_matches_its_declared_shape() -> None:
    """The table encodes what the pack brief describes: a median near 25 000 TRY."""
    table = load_table(TABLE_DIR, "balances")
    median_kurus = table.values[len(table.values) // 2]
    assert 24_000_00 <= median_kurus <= 26_000_00, f"median is {median_kurus / 100:.2f} TRY"
