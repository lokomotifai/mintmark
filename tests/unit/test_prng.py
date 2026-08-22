"""The PRNG reproduces its committed vectors, exactly, forever.

These vectors were generated from the written specification rather than from the
implementation, so they attest to the algorithm and not to a past version of the
code. A refactor that changes any value here is not a refactor: it changes the
bytes every published manifest promises to reproduce.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mintmark.engine.prng import MASK64, SplitMix64

VECTORS = json.loads(
    (Path(__file__).resolve().parents[1] / "golden" / "prng_vectors.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.golden
@pytest.mark.parametrize("case", VECTORS["vectors"], ids=lambda c: f"seed-{c['seed']}")
def test_committed_vectors_reproduce_exactly(case: dict[str, object]) -> None:
    seed = int(str(case["seed"]))
    expected = [int(v) for v in case["outputs"]]  # type: ignore[union-attr]
    stream = SplitMix64(seed)
    actual = [stream.next_u64() for _ in range(len(expected))]
    assert actual == expected


def test_every_output_fits_in_u64() -> None:
    stream = SplitMix64(0xDEAD_BEEF)
    for _ in range(2048):
        value = stream.next_u64()
        assert 0 <= value <= MASK64


def test_two_generators_from_one_seed_agree() -> None:
    """A stream is a pure function of its seed, so re-deriving reproduces it."""
    a, b = SplitMix64(12345), SplitMix64(12345)
    assert [a.next_u64() for _ in range(64)] == [b.next_u64() for _ in range(64)]


def test_adjacent_seeds_do_not_produce_adjacent_streams() -> None:
    """The finalizer's job is to decorrelate nearby seeds; check that it does."""
    a = [SplitMix64(0).next_u64() for _ in range(1)]
    b = [SplitMix64(1).next_u64() for _ in range(1)]
    assert a != b
    zero, one = SplitMix64(0), SplitMix64(1)
    overlap = {zero.next_u64() for _ in range(256)} & {one.next_u64() for _ in range(256)}
    assert not overlap, "streams from adjacent seeds share outputs"


def test_seed_is_masked_to_64_bits() -> None:
    assert SplitMix64((1 << 64) + 7).state == 7


@pytest.mark.parametrize("bad", [-1, -(1 << 70)])
def test_negative_seed_is_refused(bad: int) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        SplitMix64(bad)


@pytest.mark.parametrize("bad", ["42", 4.2, None])
def test_non_integer_seed_is_refused(bad: object) -> None:
    with pytest.raises(TypeError, match="must be an int"):
        SplitMix64(bad)  # type: ignore[arg-type]


def test_repr_shows_state_without_leaking_a_promise() -> None:
    assert repr(SplitMix64(255)) == "SplitMix64(state=0x00000000000000ff)"
