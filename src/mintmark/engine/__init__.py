"""Deterministic generation primitives.

This package imports only the standard library. That constraint is what makes
the determinism claim checkable: every value the engine produces is a function
of a seed and a site path, computed with integer arithmetic that behaves
identically on every supported platform.

`import-linter` enforces the stdlib-only rule in required CI.
"""

from mintmark.engine.draws import (
    Draw,
    bounded,
    datetime_in_window,
    weighted_index,
)
from mintmark.engine.fold import fold, fold_for_local_part
from mintmark.engine.prng import SplitMix64
from mintmark.engine.streams import StreamFactory, derive_stream_seed

__all__ = [
    "Draw",
    "SplitMix64",
    "StreamFactory",
    "bounded",
    "datetime_in_window",
    "derive_stream_seed",
    "fold",
    "fold_for_local_part",
    "weighted_index",
]
