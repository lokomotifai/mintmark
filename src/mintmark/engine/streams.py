"""Stream derivation: one independent substream per generation site.

Every value a mint emits is drawn from a stream derived from the master seed and
a stable site path such as ``customer/17/first_name``. Two consequences follow,
and both are load-bearing:

Order independence. Because a site's stream depends only on its own path, the
engine may evaluate sites in any order and still produce the same value at each
one. Generation order is nevertheless fixed elsewhere, so that sequential
identifiers and reference assignment stay stable.

Isolation. Adding a field to a record type shifts no other field's values. With
a single shared stream, inserting one draw would shift every subsequent draw and
silently invalidate every previously published manifest.

The separator is not decoration. Joining variable-length fields without one lets
a pack named ``ab`` at version ``c`` hash identically to a pack named ``a`` at
version ``bc``, which would alias two different streams into one and produce a
determinism bug that only appears for particular name and version pairs.
"""

from __future__ import annotations

import hashlib

from mintmark.engine.prng import SplitMix64

MASK64 = 0xFFFF_FFFF_FFFF_FFFF

# A single NUL byte between fields. Chosen because it cannot appear in any of
# the UTF-8 encoded field values it separates.
SEPARATOR = b"\x00"


def derive_stream_seed(
    *,
    seed: int,
    engine_major: int,
    pack_name: str,
    pack_version: str,
    recipe_name: str,
    site_path: str,
) -> int:
    """Return the u64 seed for one generation site.

    The digest input is

        seed_be8 || 0x00 || engine_major_ascii || 0x00 || pack_name || 0x00
                 || pack_version || 0x00 || recipe_name || 0x00 || site_path

    and the stream seed is the first eight bytes of the SHA-256 of that input,
    big-endian.
    """
    if not 0 <= seed <= MASK64:
        raise ValueError(f"seed must fit in u64, got {seed}")
    if engine_major < 0:
        raise ValueError(f"engine_major must be non-negative, got {engine_major}")

    parts: tuple[bytes, ...] = (
        seed.to_bytes(8, "big"),
        str(engine_major).encode("ascii"),
        pack_name.encode("utf-8"),
        pack_version.encode("utf-8"),
        recipe_name.encode("utf-8"),
        site_path.encode("utf-8"),
    )
    digest = hashlib.sha256(SEPARATOR.join(parts)).digest()
    return int.from_bytes(digest[:8], "big")


class StreamFactory:
    """Binds a mint's fixed context so call sites pass only a site path.

    One factory exists per mint. Call sites ask for a stream by path and receive
    a fresh generator positioned at that path's start, which is what makes a
    site's values independent of when it is evaluated.
    """

    __slots__ = ("_engine_major", "_pack_name", "_pack_version", "_recipe_name", "_seed")

    def __init__(
        self,
        *,
        seed: int,
        engine_major: int,
        pack_name: str,
        pack_version: str,
        recipe_name: str,
    ) -> None:
        if not 0 <= seed <= MASK64:
            raise ValueError(f"seed must fit in u64, got {seed}")
        self._seed = seed
        self._engine_major = engine_major
        self._pack_name = pack_name
        self._pack_version = pack_version
        self._recipe_name = recipe_name

    @property
    def seed(self) -> int:
        return self._seed

    def stream(self, site_path: str) -> SplitMix64:
        """Return the stream for ``site_path``.

        Calling twice with the same path returns two generators at the same
        position, not one shared generator. That is deliberate: a site is a
        pure function of its path, so re-deriving it must reproduce it.
        """
        if not site_path:
            raise ValueError("site_path must not be empty")
        return SplitMix64(
            derive_stream_seed(
                seed=self._seed,
                engine_major=self._engine_major,
                pack_name=self._pack_name,
                pack_version=self._pack_version,
                recipe_name=self._recipe_name,
                site_path=site_path,
            )
        )

    def __repr__(self) -> str:
        return (
            f"StreamFactory(seed={self._seed}, engine_major={self._engine_major}, "
            f"pack={self._pack_name}@{self._pack_version}, recipe={self._recipe_name})"
        )
