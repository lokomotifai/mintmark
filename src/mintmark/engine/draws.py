"""Bounded and weighted draws, without floating point anywhere.

Two rules govern this module.

Rejection sampling, not modulo. Reducing a 64-bit output modulo ``n``
over-represents the first ``2**64 mod n`` residues. The bias is small for small
``n`` and entirely real for large ones, and a synthetic dataset whose purpose is
to be a fair test fixture cannot carry a skew nobody declared. Draws are
therefore retried until they land in an unbiased window.

Integers throughout. Weights arrive from packs as decimal strings and are scaled
to integers before any comparison. A float would make the result depend on the
platform's rounding, which is the one thing the determinism claim cannot
tolerate.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from mintmark.engine.prng import SplitMix64

MASK64 = 0xFFFF_FFFF_FFFF_FFFF
TWO64 = 1 << 64


@dataclass(frozen=True, slots=True)
class Draw:
    """One drawn value together with the number of rejections it cost.

    The rejection count is returned rather than hidden so that a property test
    can assert the sampler is actually rejecting, and so that a pathological
    bound shows up as a measurement rather than as a hang.
    """

    value: int
    rejections: int


def bounded_with_stats(stream: SplitMix64, n: int) -> Draw:
    """Draw uniformly from ``[0, n)`` by rejection sampling."""
    if n <= 0:
        raise ValueError(f"bound must be positive, got {n}")
    if n > TWO64:
        raise ValueError(f"bound exceeds the 64-bit sampler domain: {n}")
    if n == 1:
        return Draw(0, 0)

    # Values at or above the limit would map unevenly onto [0, n), so they are
    # discarded rather than folded in.
    limit = TWO64 - (TWO64 % n)
    rejections = 0
    while True:
        candidate = stream.next_u64()
        if candidate < limit:
            return Draw(candidate % n, rejections)
        rejections += 1


def bounded(stream: SplitMix64, n: int) -> int:
    """Draw uniformly from ``[0, n)``."""
    return bounded_with_stats(stream, n).value


def bounded_range(stream: SplitMix64, low: int, high: int) -> int:
    """Draw uniformly from the inclusive range ``[low, high]``."""
    if high < low:
        raise ValueError(f"empty range: [{low}, {high}]")
    return low + bounded(stream, high - low + 1)


def _decimal_places(value: Decimal) -> int:
    """Return the number of decimal places in a finite Decimal.

    `Decimal.as_tuple().exponent` is an int for finite values and one of the
    strings "n", "N", or "F" for NaN and infinity. Those are rejected here
    rather than allowed to reach the arithmetic: a weight or a rate that is not
    a finite number is invalid input, and letting it through would produce a
    draw nobody declared.
    """
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        raise ValueError(f"{value!r} is not a finite decimal")
    return max(0, -exponent)


def scale_weights(weights: list[str]) -> list[int]:
    """Convert decimal-string weights to integers at a common scale.

    Packs declare weights as strings precisely so that ``0.1`` means one tenth
    rather than the nearest binary approximation of it. The common scale is the
    largest number of decimal places any weight uses, so no weight loses
    precision and no float is constructed at any point.
    """
    if not weights:
        raise ValueError("weights must not be empty")

    decimals: list[Decimal] = []
    for raw in weights:
        if not isinstance(raw, str):
            raise TypeError(f"weights must be decimal strings, got {type(raw).__name__}")
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise ValueError(f"weight {raw!r} is not a decimal string") from exc
        if not value.is_finite():
            raise ValueError(f"weight {raw!r} is not a finite number")
        if value < 0:
            raise ValueError(f"weight {raw!r} is negative")
        decimals.append(value)

    places = max(_decimal_places(d) for d in decimals)
    factor = Decimal(10) ** places
    scaled = [int(d * factor) for d in decimals]

    if sum(scaled) == 0:
        raise ValueError("weights sum to zero")
    return scaled


def weighted_index(stream: SplitMix64, weights: list[str]) -> int:
    """Draw an index from ``weights``, proportionally, in declaration order.

    Declaration order is part of the contract. Sorting or normalizing the
    weights first would change which index a given draw selects and therefore
    change emitted bytes for a fixed seed.
    """
    scaled = scale_weights(weights)
    total = sum(scaled)
    target = bounded(stream, total)
    cumulative = 0
    for index, weight in enumerate(scaled):
        cumulative += weight
        if target < cumulative:
            return index
    # Unreachable: target < total == cumulative after the final iteration.
    raise AssertionError("weighted_index fell through its cumulative scan")


def boolean(stream: SplitMix64, rate: str) -> bool:
    """Return True with probability ``rate``, given as a decimal string.

    Used for optional template segments and for null rates. A rate of exactly
    ``0`` or ``1`` short-circuits without consuming a draw, so that turning a
    feature fully off does not shift the stream for everything after it.
    """
    try:
        probability = Decimal(rate)
    except InvalidOperation as exc:
        raise ValueError(f"rate {rate!r} is not a decimal string") from exc
    if not probability.is_finite():
        raise ValueError(f"rate {rate!r} is not a finite number")
    if not Decimal(0) <= probability <= Decimal(1):
        raise ValueError(f"rate must lie in [0, 1], got {rate!r}")
    if probability == 0:
        return False
    if probability == 1:
        return True

    scale = 10 ** _decimal_places(probability)
    threshold = int(probability * scale)
    return bounded(stream, scale) < threshold


def datetime_in_window(stream: SplitMix64, start_epoch: int, end_epoch: int) -> int:
    """Draw an integer second in the half-open window ``[start, end)``.

    Seconds are integers so that a timestamp never depends on float rounding,
    and the window is half-open so that two adjacent windows tile without
    overlapping.
    """
    if end_epoch <= start_epoch:
        raise ValueError(f"window end must follow its start: [{start_epoch}, {end_epoch})")
    return start_epoch + bounded(stream, end_epoch - start_epoch)
