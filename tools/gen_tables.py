#!/usr/bin/env python3
"""Offline generator for fixed-point inverse-CDF tables.

Cross-platform byte determinism forbids `math.log` and `math.exp` in the mint
path, because libm results differ across platforms and across libm versions on
one platform. A log-normal amount computed at mint time would therefore produce
different bytes on Linux and macOS for the same seed, which would break the one
claim the product rests on.

The resolution is to move the transcendental work here, offline, once, and to
commit the result. This script may use `math`; nothing under `src/` may. It runs
by hand when a pack declares a parameterization that does not yet have a table,
and never implicitly as part of a mint.

Each table is 1024 knots of an inverse cumulative distribution function,
evaluated at the midpoints of equal-probability intervals and stored as integers
at a declared scale. The mint path interpolates between knots in integer
arithmetic only.

    python tools/gen_tables.py --list
    python tools/gen_tables.py --write
    python tools/gen_tables.py --verify

`--verify` regenerates every table and compares against what is committed. It is
the check that proves the committed tables were produced by this script and not
edited by hand.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TABLE_DIR = REPO_ROOT / "assets" / "tables"

KNOTS = 1024
SCALE = 100  # values are stored in kurus, so the scale is 1 TRY = 100 kurus


@dataclass(frozen=True)
class LogNormalSpec:
    """A log-normal parameterization a pack may declare by name.

    `median_try` fixes mu, because for a log-normal the median is exp(mu), which
    is the parameter a pack author can reason about. `sigma` sets the spread of
    the tail. Both are recorded in the table file so a reader can see what the
    numbers mean without reading this script.
    """

    name: str
    median_try: int
    sigma: float
    minimum_kurus: int
    maximum_kurus: int
    description: str

    @property
    def mu(self) -> float:
        return math.log(self.median_try * SCALE)


# The parameterizations the example fixture pack and the sector-contract
# conformance fixture need. A pack declaring a name absent from this list is a
# missing table, which is a core change rather than a pack workaround.
SPECS: tuple[LogNormalSpec, ...] = (
    LogNormalSpec(
        name="balances",
        median_try=25_000,
        sigma=1.35,
        minimum_kurus=0,
        maximum_kurus=500_000_000,
        description="Retail account balances. Median near 25 000 TRY with a long upper tail.",
    ),
    LogNormalSpec(
        name="txn_amounts",
        median_try=850,
        sigma=1.10,
        minimum_kurus=100,
        maximum_kurus=50_000_000,
        description="Retail transaction amounts. Median near 850 TRY.",
    ),
)


def inverse_cdf_knots(spec: LogNormalSpec) -> list[int]:
    """Evaluate the inverse CDF at the midpoint of each equal-probability bin.

    Midpoints rather than edges: the first and last edges are 0 and 1, where the
    log-normal quantile is unbounded. Midpoints keep every knot finite without
    special-casing the ends.
    """
    knots: list[int] = []
    for index in range(KNOTS):
        probability = (index + 0.5) / KNOTS
        # Inverse CDF of the log-normal: exp(mu + sigma * probit(p)).
        quantile = math.exp(spec.mu + spec.sigma * _probit(probability))
        value = int(round(quantile))
        knots.append(max(spec.minimum_kurus, min(spec.maximum_kurus, value)))
    return knots


def _probit(probability: float) -> float:
    """The standard normal inverse CDF, from the error function.

    `math.erf` is monotonic and continuous, so bisection converges reliably and
    the result does not depend on a rational approximation whose coefficients we
    would then have to justify. Sixty iterations is far past double precision.
    """
    if not 0.0 < probability < 1.0:
        raise ValueError(f"probability must lie strictly inside (0, 1), got {probability}")
    low, high = -40.0, 40.0
    for _ in range(200):
        middle = (low + high) / 2.0
        cumulative = 0.5 * (1.0 + math.erf(middle / math.sqrt(2.0)))
        if cumulative < probability:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def render(spec: LogNormalSpec) -> str:
    payload = {
        "name": spec.name,
        "distribution": "lognormal",
        "knots": KNOTS,
        "unit": "kurus",
        "parameters": {
            "median_try": spec.median_try,
            "sigma": spec.sigma,
            "minimum_kurus": spec.minimum_kurus,
            "maximum_kurus": spec.maximum_kurus,
        },
        "description": spec.description,
        "generated_by": "tools/gen_tables.py",
        "note": (
            "Inverse CDF evaluated at equal-probability bin midpoints. The mint "
            "path interpolates between these knots in integer arithmetic only and "
            "never calls a transcendental function."
        ),
        "values": inverse_cdf_knots(spec),
    }
    return json.dumps(payload, indent=2, sort_keys=False) + "\n"


def checksum_lines(rendered: dict[str, str]) -> str:
    lines = [
        f"{hashlib.sha256(text.encode('utf-8')).hexdigest()}  {name}.json"
        for name, text in sorted(rendered.items())
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list known parameterizations")
    group.add_argument("--write", action="store_true", help="generate and write the tables")
    group.add_argument(
        "--verify", action="store_true", help="regenerate and compare, write nothing"
    )
    args = parser.parse_args(argv)

    if args.list:
        for spec in SPECS:
            print(f"{spec.name}: median {spec.median_try} TRY, sigma {spec.sigma}")
        return 0

    rendered = {spec.name: render(spec) for spec in SPECS}
    sums = checksum_lines(rendered)

    if args.write:
        TABLE_DIR.mkdir(parents=True, exist_ok=True)
        for name, text in rendered.items():
            (TABLE_DIR / f"{name}.json").write_text(text, encoding="utf-8")
        (TABLE_DIR / "CHECKSUMS").write_text(sums, encoding="utf-8")
        print(f"wrote {len(rendered)} table(s) and CHECKSUMS to {TABLE_DIR}")
        return 0

    differences: list[str] = []
    for name, text in rendered.items():
        path = TABLE_DIR / f"{name}.json"
        if not path.exists():
            differences.append(f"{name}.json is missing")
        elif path.read_text(encoding="utf-8") != text:
            differences.append(f"{name}.json differs from what this script generates")
    checksums = TABLE_DIR / "CHECKSUMS"
    if not checksums.exists():
        differences.append("CHECKSUMS is missing")
    elif checksums.read_text(encoding="utf-8") != sums:
        differences.append("CHECKSUMS differs")

    if differences:
        for line in differences:
            print(f"gen_tables: {line}", file=sys.stderr)
        print(
            "\nCommitted tables do not match this script. Either the script changed, "
            "which is a determinism-affecting change, or a table was edited by hand, "
            "which is never correct.",
            file=sys.stderr,
        )
        return 1

    print(f"gen_tables: no difference, {len(rendered)} table(s) verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
