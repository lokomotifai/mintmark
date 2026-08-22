"""The invariants that can only be checked on a real mint's output.

A generator can be correct in isolation and still produce a dataset that
violates the product's promises once everything is composed. These tests run a
mint and then interrogate the artifacts, which is the same vantage point a
consumer has.
"""

from __future__ import annotations

import json
import re
import socket
from pathlib import Path

import pytest

from mintmark.annotate import ALL_LABELS
from mintmark.lexicons import load as load_denylist
from mintmark.mint import asset_dir, mint

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK = REPO_ROOT / "packs" / "example"
CONFORMANCE = REPO_ROOT / "tests" / "conformance" / "pack"


@pytest.fixture(scope="module")
def minted(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("invariants") / "run"
    mint(pack=CONFORMANCE, recipe="full", seed=20260822, out=out, invocation="pytest")
    return out


def read_all(directory: Path) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(directory.rglob("*")) if path.is_file()
    )


# Invariant 6: no network at mint time.


class _SocketGuard:
    """Replaces socket.socket so that any attempt to open one fails loudly."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise AssertionError(
            "a mint attempted to open a socket. Minting performs no network input "
            "or output, and that is a stated property of the product rather than "
            "an implementation detail."
        )


def test_minting_with_sockets_disabled_succeeds(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(socket, "socket", _SocketGuard)
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("mint opened a connection")),
    )
    out = tmp_path / "offline"
    summary = mint(
        pack=PACK,
        recipe="demo",
        seed=42,
        out=out,
        records={"customer": 25, "transaction": 25},
        invocation="pytest",
    )
    assert summary.record_counts == {"customer": 25, "transaction": 25}
    assert (out / "MINTMARK.json").exists()


def test_the_socket_guard_would_actually_fire(monkeypatch) -> None:
    """A guard that cannot trip proves nothing about what it guards."""
    monkeypatch.setattr(socket, "socket", _SocketGuard)
    with pytest.raises(AssertionError, match="attempted to open a socket"):
        socket.socket()


# Invariant 7: no real-brand leakage.


def test_no_real_institution_name_appears_in_minted_output(minted: Path) -> None:
    denylist = load_denylist(asset_dir("denylist") / "institutions-tr.txt")
    hits = denylist.scan(read_all(minted))
    assert not hits, "\n".join(hit.render() for hit in hits)


def test_no_real_institution_name_appears_in_the_committed_goldens() -> None:
    denylist = load_denylist(asset_dir("denylist") / "institutions-tr.txt")
    golden = REPO_ROOT / "tests" / "golden" / "demo-run"
    hits = denylist.scan(read_all(golden))
    assert not hits, "\n".join(hit.render() for hit in hits)


def test_no_real_institution_name_appears_in_any_shipped_template() -> None:
    denylist = load_denylist(asset_dir("denylist") / "institutions-tr.txt")
    for templates in (PACK / "templates", CONFORMANCE / "templates"):
        hits = denylist.scan(read_all(templates))
        assert not hits, "\n".join(hit.render() for hit in hits)


# Invariant 8: reserved domains only.

_DOMAIN = re.compile(r"@([A-Za-z0-9.-]+)")
RESERVED = {"example.com", "example.net", "example.org"}


def test_every_emitted_address_uses_a_reserved_documentation_name(minted: Path) -> None:
    """RFC 2606 and RFC 6761 names cannot be registered by anyone."""
    offenders: list[str] = []
    for host in set(_DOMAIN.findall(read_all(minted))):
        lowered = host.lower().rstrip(".")
        if lowered not in RESERVED and not lowered.endswith(".example"):
            offenders.append(host)
    assert not offenders, f"addresses outside the reserved space: {sorted(offenders)}"


def test_the_committed_goldens_also_stay_inside_the_reserved_space() -> None:
    golden = REPO_ROOT / "tests" / "golden" / "demo-run"
    offenders = [
        host
        for host in set(_DOMAIN.findall(read_all(golden)))
        if host.lower() not in RESERVED and not host.lower().endswith(".example")
    ]
    assert not offenders, f"addresses outside the reserved space: {sorted(offenders)}"


# Invariant 12: referential integrity, checked on the artifacts.


def test_no_reference_dangles_in_a_real_mint(minted: Path) -> None:
    def ids(name: str) -> set[str]:
        lines = (minted / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
        return {json.loads(line)[f"{name}_id"] for line in lines if line.strip()}

    customers = ids("customer")
    accounts = ids("account")

    for line in (minted / "account.jsonl").read_text(encoding="utf-8").splitlines():
        assert json.loads(line)["customer_id"] in customers

    for name in ("card", "transaction"):
        for line in (minted / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
            assert json.loads(line)["account_id"] in accounts, (
                f"{name} references a missing account"
            )


def test_sequential_identifiers_run_from_zero_without_gaps(minted: Path) -> None:
    """The id field name comes from the declaration, not from a naming guess.

    The conformance fixture calls a transaction's identifier `txn_id`, following
    the banking brief. A test that assumed `<type>_id` would pass on some record
    types and fail on the ones that matter.
    """
    from mintmark.packs.model import load_pack

    pack = load_pack(CONFORMANCE)
    for record_type in pack.record_types:
        id_field = record_type.fields[0].name
        path = minted / f"{record_type.type_name}.jsonl"
        lines = path.read_text(encoding="utf-8").splitlines()
        observed = [json.loads(line)[id_field] for line in lines if line.strip()]
        expected = [f"{record_type.id_prefix}-{index:08d}" for index in range(len(observed))]
        assert observed == expected, f"{record_type.type_name} identifiers are not sequential"


# Invariant 10: taxonomy closure, checked on the artifacts.


def test_every_label_in_every_sidecar_is_in_the_closed_set(minted: Path) -> None:
    known = {label.value for label in ALL_LABELS}
    for sidecar in sorted(minted.glob("*.labels.jsonl")):
        for line in sidecar.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            for span in json.loads(line)["spans"]:
                assert span["label"] in known, f"{sidecar.name}: unknown label {span['label']!r}"


def test_every_span_in_every_sidecar_re_extracts(minted: Path) -> None:
    """Invariant 5, checked against emitted files rather than the recorder."""
    for sidecar in sorted(minted.glob("*.labels.jsonl")):
        stem = sidecar.name.removesuffix(".labels.jsonl")
        bodies = {
            next(v for k, v in json.loads(line).items() if k.endswith("_id")): json.loads(line)[
                "body"
            ]
            for line in (minted / f"{stem}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
        for line in sidecar.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            text = bodies[record["doc_id"]]
            for span in record["spans"]:
                surface = text[span["start"] : span["end"]]
                assert surface.strip(), (
                    f"{sidecar.name}: span [{span['start']}, {span['end']}) for "
                    f"{span['label']} covers no text"
                )


# Invariant 11: no floats reach emitted data.


def test_no_emitted_json_value_is_a_float(minted: Path) -> None:
    for path in sorted(minted.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            _assert_no_float(json.loads(line), path.name)


def _assert_no_float(value: object, where: str) -> None:
    if isinstance(value, float):
        raise AssertionError(f"{where}: a float reached emitted data: {value!r}")
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_float(item, where)
    elif isinstance(value, list):
        for item in value:
            _assert_no_float(item, where)


# Timestamps carry the fixed Turkish offset.


def test_every_emitted_timestamp_carries_the_verified_offset(minted: Path) -> None:
    """Turkey is permanently UTC+3, verified against the IANA database."""
    for line in (minted / "transaction.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        assert json.loads(line)["ts"].endswith("+03:00")


# The safe-mode sweep, and the false positive that once fired inside a digest.


def test_the_sweep_ignores_digests_and_offsets_in_sidecars(minted: Path) -> None:
    """A sidecar carries no data, so nothing in it can be a leaked identifier.

    This test exists because the sweep once read raw file text and swept the
    sidecars too. A SHA-256 digest is sixty-four hex characters and regularly
    contains a ten-digit run; about one such run in ten satisfies the VKN check by
    chance. The sweep fired on its own checksum, and a safety check that cries
    wolf is a safety check somebody switches off.
    """
    from mintmark.api import verify as verify_dataset

    report = verify_dataset(minted)
    assert report.checksum_valid_identifiers == 0
    assert report.ok, report.problems


def test_the_sweep_still_catches_a_planted_valid_identifier(minted: Path, tmp_path: Path) -> None:
    """Narrowing the sweep must not have narrowed it into uselessness."""
    import json
    import shutil

    from mintmark.api import verify as verify_dataset
    from mintmark.identifiers import IdentifierPolicy, vkn
    from mintmark.engine.prng import SplitMix64
    from mintmark.manifest import file_digest, render_sums
    from mintmark.manifest.document import MANIFEST_FILENAME
    from mintmark.manifest.sums import SUMS_FILENAME

    target = tmp_path / "planted"
    shutil.copytree(minted, target)

    valid = vkn.generate(SplitMix64(3), IdentifierPolicy.VALIDATOR)
    assert vkn.is_checksum_valid(valid)

    path = target / "transaction.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["vkn"] = valid
    lines[0] = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    manifest_path = target / MANIFEST_FILENAME
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    sums = {}
    for output in document["outputs"]:
        if output["path"] == "transaction.jsonl":
            output["sha256"] = file_digest(path)
            output["bytes"] = path.stat().st_size
        sums[output["path"]] = output["sha256"]
    manifest_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    sums[MANIFEST_FILENAME] = file_digest(manifest_path)
    (target / SUMS_FILENAME).write_text(render_sums(sums), encoding="utf-8")

    report = verify_dataset(target)
    assert report.checksum_valid_identifiers >= 1
    assert any("checksum-valid VKN" in problem for problem in report.problems)


def test_a_digit_run_inside_a_longer_token_is_not_a_candidate() -> None:
    """The anchoring that stopped the false positive, asserted directly."""
    from mintmark.manifest.verify import _CANDIDATE

    assert _CANDIDATE.findall("1234567890") == ["1234567890"]
    assert _CANDIDATE.findall("ab1234567890cd") == []
    assert _CANDIDATE.findall("26bf03eefa2dec60a2033640190cf612") == []
    assert _CANDIDATE.findall("TR990000000000000000000001") == ["TR990000000000000000000001"]
