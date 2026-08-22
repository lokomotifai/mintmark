"""SplitMix64, in pure Python over 64-bit modular arithmetic.

The generator is specified rather than imported so that its output is fixed by
this repository and not by a dependency's release schedule. Every constant and
every shift below is part of the determinism contract: changing one changes the
bytes every published manifest promises to reproduce, which is a major version
event even though no signature changes.

Pure Python is also the point. A native implementation would be faster and would
put the byte-level result at the mercy of a compiler, a platform, and a build
flag. Minting is not on a hot path that justifies that trade.
"""

from __future__ import annotations

MASK64 = 0xFFFF_FFFF_FFFF_FFFF

# The SplitMix64 constants. GAMMA is the odd increment that advances the state;
# the two multipliers and three shifts form the finalizer that mixes it.
GAMMA = 0x9E37_79B9_7F4A_7C15
MIX_A = 0xBF58_476D_1CE4_E5B9
MIX_B = 0x94D0_49BB_1331_11EB


class SplitMix64:
    """A single independent pseudorandom stream.

    Construct one per generation site through
    :class:`mintmark.engine.streams.StreamFactory`, never by seeding this class
    directly from application code. A stream shared between two sites couples
    them, and coupled sites make generation order significant, which is exactly
    what the site-path derivation exists to prevent.
    """

    __slots__ = ("_state",)

    def __init__(self, seed: int) -> None:
        if not isinstance(seed, int):
            raise TypeError(f"seed must be an int, got {type(seed).__name__}")
        if seed < 0:
            raise ValueError(f"seed must be a non-negative u64, got {seed}")
        self._state = seed & MASK64

    @property
    def state(self) -> int:
        """The current 64-bit state.

        Exposed so that a caller can record or assert a stream position. It is
        not a public serialization format and carries no compatibility promise.
        """
        return self._state

    def next_u64(self) -> int:
        """Advance the state and return the next 64-bit output."""
        self._state = (self._state + GAMMA) & MASK64
        z = self._state
        z = ((z ^ (z >> 30)) * MIX_A) & MASK64
        z = ((z ^ (z >> 27)) * MIX_B) & MASK64
        return (z ^ (z >> 31)) & MASK64

    def __repr__(self) -> str:
        return f"SplitMix64(state=0x{self._state:016x})"
