"""Record generation: declared order, stable identifiers, references that hold.

Three properties make the output reproducible and usable.

Order is fixed by each record type's declared position, and within a type by
index. Streams are order-independent, so this fixed order is not needed for field
values; it is needed for sequential identifiers and for reference assignment,
both of which depend on how many records came before.

Identifiers are `PREFIX-%08d` over the index, so `CUST-00000017` is the
eighteenth customer and stays the eighteenth customer across every re-mint.

References never dangle. Children are assigned to parents from a stream keyed by
the parent index, honoring the declared per-parent count distribution. When the
requested child count does not match what the distribution produces, the
remainder is distributed deterministically from the lowest parent index upward
and the achieved proportions are recorded in the manifest, rather than the count
being silently changed to whatever the distribution happened to give.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

from mintmark.engine.draws import bounded, scale_weights, weighted_index, weighted_index_scaled
from mintmark.engine.streams import StreamFactory

# One record is an ordered mapping of field name to emitted value. Order is the
# declaration order of the record type, which is what the canonical serialization
# writes and what a consumer's schema expects.
Record = dict[str, Any]


def entity_id(prefix: str, index: int) -> str:
    """`PREFIX-00000017`, stable across every re-mint of the same recipe."""
    if index < 0:
        raise ValueError(f"record index must be non-negative, got {index}")
    return f"{prefix}-{index:08d}"


@dataclass(slots=True)
class DistributionTally:
    """Target against achieved proportions for one declared distribution.

    Recorded in the manifest so that a consumer can see what the data actually
    contains rather than what it was asked to contain. The two differ whenever a
    count is small relative to the number of buckets, and hiding that difference
    would make the manifest a statement of intent rather than of fact.
    """

    site: str
    targets: dict[str, str]
    counts: dict[str, int] = dataclass_field(default_factory=dict)

    def observe(self, value: str) -> None:
        self.counts[value] = self.counts.get(value, 0) + 1

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def achieved(self) -> dict[str, str]:
        total = self.total
        if total == 0:
            return dict.fromkeys(self.targets, "0")
        # Proportions are decimal strings, never floats: the manifest is compared
        # byte for byte by `reproduce`.
        return {key: _proportion(self.counts.get(key, 0), total) for key in sorted(self.targets)}

    def within_tolerance(self, tolerance: str = "0.02") -> bool:
        """Compare achieved against target using integers only.

        The tolerance flag is recorded in the manifest, and the manifest is
        compared byte for byte by `reproduce`. Float arithmetic here would be
        deterministic in practice and still wrong in principle: the discipline is
        that nothing in the mint path decides an emitted value by binary rounding.
        """
        total = self.total
        if total == 0:
            return True
        limit = _scaled(tolerance)
        for key, target in self.targets.items():
            observed = (self.counts.get(key, 0) * SCALE + total // 2) // total
            if abs(observed - _scaled(target)) > limit:
                return False
        return True


# Proportions are held as integers at four decimal places throughout.
SCALE = 10_000


def _scaled(decimal_string: str) -> int:
    """Parse a decimal string into an integer at SCALE, without a float."""
    whole, _, fraction = decimal_string.partition(".")
    fraction = (fraction + "0000")[:4]
    return int(whole or "0") * SCALE + int(fraction)


def _proportion(count: int, total: int) -> str:
    """Four decimal places, computed with integers and formatted as a string."""
    scaled = (count * SCALE + total // 2) // total
    return f"{scaled // SCALE}.{scaled % SCALE:04d}"


def assign_children(
    factory: StreamFactory,
    *,
    site: str,
    parent_count: int,
    child_count: int,
    counts: tuple[int, ...],
    weights: tuple[str, ...],
) -> list[int]:
    """Return one parent index per child, honoring the count distribution.

    The distribution says how many children each parent should have. The recipe
    says how many children exist. The requested total must fit the declared
    per-parent minimum and maximum; deterministic adjustment never crosses those
    bounds.
    """
    if parent_count <= 0:
        if child_count > 0:
            raise ValueError(
                f"{site}: {child_count} children requested but the parent type is empty; "
                "a reference cannot dangle"
            )
        return []
    if child_count == 0:
        # A recipe may explicitly disable a record type. Cardinality applies
        # when that relationship is present, not to a type the recipe omits.
        return []

    minimum = min(counts)
    maximum = max(counts)
    minimum_total = parent_count * minimum
    maximum_total = parent_count * maximum
    if not minimum_total <= child_count <= maximum_total:
        raise ValueError(
            f"{site}: {child_count} children cannot satisfy {minimum}..{maximum} "
            f"children for each of {parent_count} parents; feasible total is "
            f"{minimum_total}..{maximum_total}"
        )

    per_parent: list[int] = []
    scaled_weights = scale_weights(list(weights))
    for parent_index in range(parent_count):
        stream = factory.stream(f"{site}/{parent_index}/count")
        per_parent.append(counts[weighted_index_scaled(stream, scaled_weights)])

    total = sum(per_parent)
    if total > child_count:
        # Trim from the highest-index parents first, so that adding records to a
        # recipe never changes the allocation of the records already there.
        surplus = total - child_count
        for parent_index in range(parent_count - 1, -1, -1):
            if surplus == 0:
                break
            take = min(per_parent[parent_index] - minimum, surplus)
            per_parent[parent_index] -= take
            surplus -= take
    elif total < child_count:
        deficit = child_count - total
        parent_index = 0
        while deficit > 0:
            selected = parent_index % parent_count
            parent_index += 1
            if per_parent[selected] < maximum:
                per_parent[selected] += 1
                deficit -= 1

    if sum(per_parent) != child_count:
        raise AssertionError(f"{site}: bounded relationship allocation did not converge")

    assignment: list[int] = []
    for parent_index, count in enumerate(per_parent):
        assignment.extend([parent_index] * count)
    return assignment


@dataclass(slots=True)
class GenerationContext:
    """Everything a field generator needs, assembled once per mint."""

    factory: StreamFactory
    record_type: str
    index: int
    parents: dict[str, Record]
    tallies: dict[str, DistributionTally]

    def site(self, field_name: str) -> str:
        return f"{self.record_type}/{self.index}/{field_name}"

    def stream(self, field_name: str) -> Any:
        return self.factory.stream(self.site(field_name))


FieldGenerator = Callable[[GenerationContext], Any]


def choose(context: GenerationContext, field_name: str, options: list[str]) -> str:
    """Uniform choice from a lexicon, drawn from the field's own stream."""
    if not options:
        raise ValueError(f"{context.site(field_name)}: cannot choose from an empty lexicon")
    return options[bounded(context.stream(field_name), len(options))]


def choose_weighted(
    context: GenerationContext,
    field_name: str,
    options: list[str],
    weights: list[str],
    tally: DistributionTally | None = None,
) -> str:
    """Weighted choice in declaration order, tallied for the manifest."""
    if len(options) != len(weights):
        raise ValueError(
            f"{context.site(field_name)}: {len(options)} options against {len(weights)} weights"
        )
    value = options[weighted_index(context.stream(field_name), weights)]
    if tally is not None:
        tally.observe(value)
    return value
