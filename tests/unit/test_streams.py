"""Stream derivation is order-independent, isolated, and unambiguous."""

from __future__ import annotations

import pytest

from mintmark.engine.streams import StreamFactory, derive_stream_seed

BASE = {
    "seed": 42,
    "engine_major": 0,
    "pack_name": "mintmark-example",
    "pack_version": "0.1.0",
    "recipe_name": "demo",
}


def factory(**overrides: object) -> StreamFactory:
    return StreamFactory(**{**BASE, **overrides})  # type: ignore[arg-type]


def test_same_site_path_reproduces_the_same_stream() -> None:
    f = factory()
    a = [f.stream("customer/17/first_name").next_u64() for _ in range(8)]
    b = [f.stream("customer/17/first_name").next_u64() for _ in range(8)]
    assert a == b


def test_evaluation_order_does_not_affect_values() -> None:
    """The whole point of per-site derivation: sites are independent."""
    f = factory()
    forward = {p: f.stream(p).next_u64() for p in ("a/0/x", "a/1/x", "a/2/x")}
    backward = {p: f.stream(p).next_u64() for p in ("a/2/x", "a/1/x", "a/0/x")}
    assert forward == backward


def test_different_site_paths_give_different_streams() -> None:
    f = factory()
    values = {f.stream(f"customer/{i}/first_name").next_u64() for i in range(512)}
    assert len(values) == 512, "site paths collided"


def test_the_nul_separator_prevents_field_boundary_aliasing() -> None:
    """Without a separator, pack "ab" at version "c" would alias "a" at "bc".

    That aliasing would not be a hypothetical: it would silently give two
    different packs the same stream for the same site path, and it would only
    show up for particular name and version pairs.
    """
    left = derive_stream_seed(
        seed=1,
        engine_major=0,
        pack_name="ab",
        pack_version="c",
        recipe_name="r",
        site_path="s",
    )
    right = derive_stream_seed(
        seed=1,
        engine_major=0,
        pack_name="a",
        pack_version="bc",
        recipe_name="r",
        site_path="s",
    )
    assert left != right


def test_every_context_field_changes_the_stream() -> None:
    baseline = derive_stream_seed(
        seed=1,
        engine_major=0,
        pack_name="p",
        pack_version="1",
        recipe_name="r",
        site_path="s",
    )
    variants = [
        {"seed": 2},
        {"engine_major": 1},
        {"pack_name": "q"},
        {"pack_version": "2"},
        {"recipe_name": "t"},
        {"site_path": "u"},
    ]
    for override in variants:
        args = {
            "seed": 1,
            "engine_major": 0,
            "pack_name": "p",
            "pack_version": "1",
            "recipe_name": "r",
            "site_path": "s",
            **override,
        }
        assert derive_stream_seed(**args) != baseline, f"{override} did not change the stream"  # type: ignore[arg-type]


def test_derived_seed_fits_in_u64() -> None:
    value = derive_stream_seed(
        seed=(1 << 64) - 1,
        engine_major=99,
        pack_name="p",
        pack_version="1",
        recipe_name="r",
        site_path="s",
    )
    assert 0 <= value < (1 << 64)


def test_turkish_characters_in_a_site_path_are_handled() -> None:
    """Site paths carry field names, and Turkish field names are legitimate."""
    f = factory()
    a = f.stream("musteri/0/dogum_tarihi").next_u64()
    b = f.stream("müşteri/0/doğum_tarihi").next_u64()
    assert a != b


def test_empty_site_path_is_refused() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        factory().stream("")


@pytest.mark.parametrize("bad", [-1, 1 << 64])
def test_out_of_range_seed_is_refused(bad: int) -> None:
    with pytest.raises(ValueError, match="u64"):
        factory(seed=bad)


def test_negative_engine_major_is_refused() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        derive_stream_seed(
            seed=1,
            engine_major=-1,
            pack_name="p",
            pack_version="1",
            recipe_name="r",
            site_path="s",
        )
