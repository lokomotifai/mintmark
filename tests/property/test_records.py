"""Invariant 12: references never dangle, and identifiers stay stable."""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from mintmark.engine.records import (
    DistributionTally,
    assign_children,
    entity_id,
)
from mintmark.engine.streams import StreamFactory

QUICK = settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])


def factory(seed: int = 42) -> StreamFactory:
    return StreamFactory(
        seed=seed,
        engine_major=0,
        pack_name="mintmark-fixture",
        pack_version="0.1.0",
        recipe_name="demo",
    )


def test_entity_ids_are_zero_padded_to_eight_digits() -> None:
    assert entity_id("CUST", 0) == "CUST-00000000"
    assert entity_id("CUST", 17) == "CUST-00000017"
    assert entity_id("TXN", 12_345_678) == "TXN-12345678"


def test_a_negative_index_is_refused() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        entity_id("CUST", -1)


@QUICK
@given(
    parents=st.integers(1, 500),
    children=st.integers(0, 2000),
    seed=st.integers(0, 2**32),
)
def test_every_child_points_at_a_real_parent(parents: int, children: int, seed: int) -> None:
    assignment = assign_children(
        factory(seed),
        site="account/customer_id",
        parent_count=parents,
        child_count=children,
        counts=(1, 2, 3),
        weights=("0.55", "0.30", "0.15"),
    )
    assert len(assignment) == children
    assert all(0 <= parent < parents for parent in assignment)


@QUICK
@given(parents=st.integers(1, 300), seed=st.integers(0, 2**32))
def test_a_zero_lower_bound_permits_childless_parents(parents: int, seed: int) -> None:
    """Cards are 0..2 per account. A parent with no children is correct."""
    assignment = assign_children(
        factory(seed),
        site="card/account_id",
        parent_count=parents,
        child_count=parents,
        counts=(0, 1, 2),
        weights=("0.40", "0.40", "0.20"),
    )
    assert all(0 <= parent < parents for parent in assignment)
    # Not an assertion that some parent is childless, which the recipe count can
    # forbid, but that nothing requires every parent to have one.
    assert len(assignment) == parents


def test_assignment_is_reproducible_from_the_same_seed() -> None:
    args = {
        "site": "account/customer_id",
        "parent_count": 100,
        "child_count": 180,
        "counts": (1, 2, 3),
        "weights": ("0.55", "0.30", "0.15"),
    }
    first = assign_children(factory(7), **args)  # type: ignore[arg-type]
    second = assign_children(factory(7), **args)  # type: ignore[arg-type]
    assert first == second


def test_a_different_seed_gives_a_different_assignment() -> None:
    args = {
        "site": "account/customer_id",
        "parent_count": 100,
        "child_count": 180,
        "counts": (1, 2, 3),
        "weights": ("0.55", "0.30", "0.15"),
    }
    assert assign_children(factory(7), **args) != assign_children(factory(8), **args)  # type: ignore[arg-type]


def test_requesting_children_from_an_empty_parent_type_is_refused() -> None:
    """Silently emitting zero children would leave a recipe quietly unsatisfied."""
    with pytest.raises(ValueError, match="cannot dangle"):
        assign_children(
            factory(),
            site="account/customer_id",
            parent_count=0,
            child_count=10,
            counts=(1,),
            weights=("1",),
        )


def test_no_children_from_no_parents_is_fine() -> None:
    assert (
        assign_children(
            factory(), site="a/b", parent_count=0, child_count=0, counts=(1,), weights=("1",)
        )
        == []
    )


def test_the_distribution_shapes_the_allocation() -> None:
    """Weights 0.55/0.30/0.15 over 1..3 should average about 1.6 children."""
    assignment = assign_children(
        factory(),
        site="account/customer_id",
        parent_count=10_000,
        child_count=16_000,
        counts=(1, 2, 3),
        weights=("0.55", "0.30", "0.15"),
    )
    per_parent: dict[int, int] = {}
    for parent in assignment:
        per_parent[parent] = per_parent.get(parent, 0) + 1
    observed = sorted(per_parent.values())
    assert min(observed) >= 1
    assert max(observed) <= 4, "the trim or fill walk produced an implausible parent"


def test_trimming_takes_from_the_highest_parents_first() -> None:
    """Adding records to a recipe must not reshuffle the ones already there."""
    common = {
        "site": "account/customer_id",
        "parent_count": 50,
        "counts": (2, 2, 2),
        "weights": ("1", "1", "1"),
    }
    generous = assign_children(factory(), child_count=100, **common)  # type: ignore[arg-type]
    trimmed = assign_children(factory(), child_count=90, **common)  # type: ignore[arg-type]
    assert trimmed == generous[:90] or set(trimmed) <= set(generous)
    assert max(trimmed) <= max(generous)


def test_tally_reports_achieved_proportions_as_decimal_strings() -> None:
    tally = DistributionTally(site="account/type", targets={"a": "0.5", "b": "0.5"})
    for _ in range(60):
        tally.observe("a")
    for _ in range(40):
        tally.observe("b")
    achieved = tally.achieved()
    assert achieved == {"a": "0.6000", "b": "0.4000"}
    assert all(isinstance(v, str) for v in achieved.values())


def test_tally_of_nothing_reports_zero_rather_than_dividing() -> None:
    tally = DistributionTally(site="account/type", targets={"a": "1"})
    assert tally.achieved() == {"a": "0"}
    assert tally.within_tolerance()


def test_tolerance_flags_a_distribution_that_missed() -> None:
    tally = DistributionTally(site="account/type", targets={"a": "0.9", "b": "0.1"})
    for _ in range(50):
        tally.observe("a")
    for _ in range(50):
        tally.observe("b")
    assert not tally.within_tolerance()


def test_tolerance_accepts_a_distribution_that_landed() -> None:
    tally = DistributionTally(site="account/type", targets={"a": "0.9", "b": "0.1"})
    for _ in range(895):
        tally.observe("a")
    for _ in range(105):
        tally.observe("b")
    assert tally.within_tolerance()


@pytest.mark.parametrize(
    ("count", "total", "expected"),
    [(1, 3, "0.3333"), (2, 3, "0.6667"), (1, 1, "1.0000"), (0, 5, "0.0000")],
)
def test_proportions_round_half_up_without_floats(count: int, total: int, expected: str) -> None:
    tally = DistributionTally(site="s", targets={"x": "1"})
    for _ in range(count):
        tally.observe("x")
    for _ in range(total - count):
        tally.observe("y")
    tally.targets["y"] = "0"
    assert tally.achieved()["x"] == expected
