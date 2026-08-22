"""Draws are unbiased, integer-only, and reject bad input rather than coercing it."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mintmark.engine.draws import (
    TWO64,
    boolean,
    bounded,
    bounded_range,
    bounded_with_stats,
    datetime_in_window,
    scale_weights,
    weighted_index,
)
from mintmark.engine.prng import SplitMix64

QUICK = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])


@QUICK
@given(seed=st.integers(0, TWO64 - 1), n=st.integers(1, 10**9))
def test_bounded_stays_in_range(seed: int, n: int) -> None:
    assert 0 <= bounded(SplitMix64(seed), n) < n


@QUICK
@given(seed=st.integers(0, TWO64 - 1), low=st.integers(-(10**6), 10**6), span=st.integers(0, 10**6))
def test_bounded_range_is_inclusive_on_both_ends(seed: int, low: int, span: int) -> None:
    high = low + span
    value = bounded_range(SplitMix64(seed), low, high)
    assert low <= value <= high


def test_bounded_is_uniform_over_a_small_alphabet() -> None:
    """A modulo sampler would skew here; rejection sampling must not.

    Chi-squared over 26 buckets with 26000 samples. The threshold is the 0.999
    critical value for 25 degrees of freedom, so a fair sampler fails this about
    one run in a thousand, and the seed is fixed so that "about" never matters.
    """
    stream = SplitMix64(20260822)
    buckets = [0] * 26
    samples = 26_000
    for _ in range(samples):
        buckets[bounded(stream, 26)] += 1

    expected = samples / 26
    chi_squared = sum((count - expected) ** 2 / expected for count in buckets)
    assert chi_squared < 52.62, f"chi-squared {chi_squared:.2f} suggests a skewed sampler"


def test_rejection_actually_happens_for_a_hostile_bound() -> None:
    """A bound just above a power of two rejects almost half of all draws.

    If this ever reports zero rejections, the sampler silently became a modulo
    reduction and the uniformity guarantee is gone.
    """
    hostile = (1 << 63) + 1
    stream = SplitMix64(7)
    total = sum(bounded_with_stats(stream, hostile).rejections for _ in range(200))
    assert total > 0, "no rejections observed; the sampler is not rejecting"


def test_bound_of_one_consumes_no_draw() -> None:
    """Turning a choice into a certainty must not shift everything after it."""
    stream = SplitMix64(99)
    before = stream.state
    assert bounded(stream, 1) == 0
    assert stream.state == before


def test_full_u64_domain_is_supported() -> None:
    stream = SplitMix64(99)
    expected = stream.next_u64()

    assert bounded(SplitMix64(99), TWO64) == expected


@pytest.mark.parametrize("bad", [TWO64 + 1, TWO64 * 2, 10**100])
def test_bound_larger_than_u64_domain_is_refused_without_drawing(bad: int) -> None:
    stream = SplitMix64(1)
    before = stream.state

    with pytest.raises(ValueError, match="exceeds the 64-bit sampler domain"):
        bounded(stream, bad)

    assert stream.state == before


@pytest.mark.parametrize("bad", [0, -1, -(10**9)])
def test_non_positive_bound_is_refused(bad: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        bounded(SplitMix64(1), bad)


def test_empty_range_is_refused() -> None:
    with pytest.raises(ValueError, match="empty range"):
        bounded_range(SplitMix64(1), 10, 9)


def test_scale_weights_preserves_declared_precision() -> None:
    assert scale_weights(["0.55", "0.30", "0.15"]) == [55, 30, 15]
    assert scale_weights(["0.925", "0.05", "0.025"]) == [925, 50, 25]
    assert scale_weights(["1", "3"]) == [1, 3]


def test_weighted_index_respects_declaration_order() -> None:
    """Index 0 must mean the first declared weight, not the largest."""
    counts = [0, 0, 0]
    stream = SplitMix64(2026)
    for _ in range(20_000):
        counts[weighted_index(stream, ["0.80", "0.15", "0.05"])] += 1
    assert counts[0] > counts[1] > counts[2]
    assert abs(counts[0] / 20_000 - 0.80) < 0.02
    assert abs(counts[1] / 20_000 - 0.15) < 0.02
    assert abs(counts[2] / 20_000 - 0.05) < 0.02


def test_zero_weight_is_never_selected() -> None:
    stream = SplitMix64(5)
    picks = {weighted_index(stream, ["1", "0", "1"]) for _ in range(2000)}
    assert 1 not in picks


@pytest.mark.parametrize(
    ("weights", "match"),
    [
        ([], "must not be empty"),
        (["0", "0"], "sum to zero"),
        (["-1", "2"], "negative"),
        (["NaN", "1"], "finite"),
        (["Infinity", "1"], "finite"),
        (["abc"], "not a decimal string"),
    ],
)
def test_invalid_weights_are_refused(weights: list[str], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        weighted_index(SplitMix64(1), weights)


def test_float_weights_are_refused_by_type() -> None:
    """A float weight would make the result depend on binary rounding."""
    with pytest.raises(TypeError, match="decimal strings"):
        scale_weights([0.5, 0.5])  # type: ignore[list-item]


def test_boolean_endpoints_short_circuit_without_consuming_a_draw() -> None:
    stream = SplitMix64(3)
    before = stream.state
    assert boolean(stream, "0") is False
    assert boolean(stream, "1") is True
    assert stream.state == before


def test_boolean_matches_its_declared_rate() -> None:
    stream = SplitMix64(1234)
    hits = sum(boolean(stream, "0.35") for _ in range(20_000))
    assert abs(hits / 20_000 - 0.35) < 0.02


@pytest.mark.parametrize(
    ("bad", "match"),
    [("-0.1", "must lie in"), ("1.1", "must lie in"), ("NaN", "finite")],
)
def test_out_of_band_rate_is_refused(bad: str, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        boolean(SplitMix64(1), bad)


@QUICK
@given(seed=st.integers(0, TWO64 - 1), start=st.integers(0, 2**31), span=st.integers(1, 2**31))
def test_datetime_window_is_half_open(seed: int, start: int, span: int) -> None:
    value = datetime_in_window(SplitMix64(seed), start, start + span)
    assert start <= value < start + span


def test_inverted_window_is_refused() -> None:
    with pytest.raises(ValueError, match="must follow its start"):
        datetime_in_window(SplitMix64(1), 100, 100)
