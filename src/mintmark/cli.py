"""The command line surface, on argparse and the standard library only.

Seven verbs, five exit codes, and a stable `--json` payload for each verb that
declares one. Those are a public contract under semantic versioning: adding a
field is a minor version, removing or retyping one is a major.

Exit codes carry meaning, because a script consuming this tool needs to tell a
malformed pack from a tampered dataset from a reproduction mismatch:

    0  success
    1  usage error
    2  invalid pack, failing closed
    3  verification failure
    4  reproduction mismatch

Error messages name the file, the location, and the rule. No stack trace reaches
a user at default verbosity: a traceback tells them about this program's
internals when what they need is which line of their pack is wrong.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mintmark.annotate import Label, pin_digest
from mintmark.identifiers import CHECKSUMMED
from mintmark.manifest import (
    MANIFEST_FILENAME,
    SUMS_FILENAME,
    read_manifest,
    render_sums,
    verify,
)
from mintmark.manifest.document import comparable
from mintmark.manifest.io import (
    MAX_CONTROL_FILE_BYTES,
    MAX_DATA_FILE_BYTES,
    DatasetIOError,
    DatasetReader,
)
from mintmark.mint import MintError, mint, packaged_pack_dir, resolve_pack, schema_dir
from mintmark.packs.loader import PackError
from mintmark.packs.model import load_pack

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_INVALID_PACK = 2
EXIT_VERIFY_FAILED = 3
EXIT_REPRODUCE_MISMATCH = 4


def _validators() -> dict[str, Any]:
    """Compose the identifier validators verification needs.

    `manifest` sits above `identifiers` in the declared dependency direction, so
    it cannot import them. This is the layer that knows about both.
    """
    return {name: engine.is_checksum_valid for name, engine in CHECKSUMMED.items()}


def _manifest_schema() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (schema_dir() / "manifest.schema.json").read_text(encoding="utf-8")
    )
    return document


def build_parser() -> argparse.ArgumentParser:
    from mintmark import __version__

    parser = argparse.ArgumentParser(
        prog="mintmark",
        description="Mint deterministic, fully synthetic, Turkish-first labeled datasets.",
    )
    parser.add_argument("--version", action="version", version=f"mintmark {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    mint_parser = subparsers.add_parser("mint", help="mint a dataset")
    mint_parser.add_argument("--pack", required=True)
    mint_parser.add_argument("--recipe", required=True)
    mint_parser.add_argument("--seed", required=True, type=int)
    mint_parser.add_argument("--out", required=True)
    mint_parser.add_argument(
        "--records",
        action="append",
        default=[],
        metavar="TYPE=N",
        help="override a recipe's count for one record type; may repeat",
    )
    mint_parser.add_argument(
        "--identifier-policy",
        choices=["safe", "validator"],
        default=None,
        help="only needed when the recipe does not name one; a recipe that does, decides",
    )
    mint_parser.add_argument("--format", choices=["jsonl", "csv"], default="jsonl")
    mint_parser.add_argument("--json", action="store_true")

    for name, help_text in (
        ("verify", "revalidate a dataset against its manifest"),
        ("reproduce", "re-mint from a manifest and byte-compare"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("directory")
        sub.add_argument(
            "--trusted-manifest-sha256",
            help="require MINTMARK.json to match this externally obtained SHA-256 digest",
        )
        sub.add_argument("--json", action="store_true")

    for name, help_text in (
        ("packcheck", "validate a pack and mini-mint it"),
        ("inspect", "print a pack's identity and declarations"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("pack")
        sub.add_argument("--json", action="store_true")

    schema_parser = subparsers.add_parser("schema", help="print a shipped JSON Schema")
    schema_parser.add_argument("which", choices=["pack", "manifest"])
    schema_parser.add_argument("--json", action="store_true")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        match args.command:
            case "mint":
                return _cmd_mint(args, _mint_invocation(args))
            case "verify":
                return _cmd_verify(args)
            case "reproduce":
                return _cmd_reproduce(args)
            case "packcheck":
                return _cmd_packcheck(args)
            case "inspect":
                return _cmd_inspect(args)
            case "schema":
                return _cmd_schema(args)
    except PackError as error:
        print(f"mintmark: {error}", file=sys.stderr)
        return EXIT_INVALID_PACK
    except MintError as error:
        print(f"mintmark: {error}", file=sys.stderr)
        return EXIT_USAGE
    except (KeyError, ValueError) as error:
        print(f"mintmark: {error}", file=sys.stderr)
        return EXIT_USAGE
    except FileNotFoundError as error:
        print(f"mintmark: {error}", file=sys.stderr)
        return EXIT_VERIFY_FAILED

    return EXIT_USAGE


def _mint_invocation(args: argparse.Namespace) -> str:
    """Record replay-relevant CLI options without publishing workstation paths."""
    tokens = [
        "mintmark",
        "mint",
        "--pack",
        "<pack>",
        "--recipe",
        args.recipe,
        "--seed",
        str(args.seed),
        "--out",
        "<output>",
        "--identifier-policy",
        args.identifier_policy,
        "--format",
        args.format,
    ]
    for override in args.records:
        tokens.extend(("--records", override))
    return shlex.join(tokens)


def _parse_record_overrides(pairs: list[str]) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for pair in pairs:
        name, separator, count = pair.partition("=")
        if not separator or not count.isdigit():
            raise ValueError(f"--records expects TYPE=N, got {pair!r}")
        overrides[name] = int(count)
    return overrides


def _cmd_mint(args: argparse.Namespace, invocation: str) -> int:
    summary = mint(
        pack=resolve_pack(args.pack),
        recipe=args.recipe,
        seed=args.seed,
        out=args.out,
        identifier_policy=args.identifier_policy,
        fmt=args.format,
        records=_parse_record_overrides(args.records),
        invocation=invocation,
    )
    if args.json:
        print(json.dumps(summary.to_json(), ensure_ascii=False, indent=2))
    else:
        for name in sorted(summary.outputs):
            print(f"wrote {name}")
        counts = ", ".join(f"{k}={v}" for k, v in sorted(summary.record_counts.items()))
        print(f"records: {counts}")
        print(f"pack digest: {summary.pack_digest}")
    return EXIT_OK


def _cmd_verify(args: argparse.Namespace) -> int:
    report = verify(
        Path(args.directory),
        schema=_manifest_schema(),
        validators=_validators(),
        expected_taxonomy_pin=pin_digest(),
        known_labels=frozenset(label.value for label in Label),
        trusted_manifest_sha256=args.trusted_manifest_sha256,
    )
    if args.json:
        print(json.dumps(report.to_json(), ensure_ascii=False, indent=2))
    else:
        print(report.render())
    return EXIT_OK if report.ok else EXIT_VERIFY_FAILED


def _cmd_reproduce(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    preflight = verify(
        directory,
        schema=_manifest_schema(),
        validators=_validators(),
        expected_taxonomy_pin=pin_digest(),
        known_labels=frozenset(label.value for label in Label),
        trusted_manifest_sha256=args.trusted_manifest_sha256,
    )
    if not preflight.ok:
        differences = [f"preflight verification: {problem}" for problem in preflight.problems]
        return _render_reproduce_result(directory, differences, args.json)

    try:
        source_reader = DatasetReader(directory)
    except (DatasetIOError, OSError, ValueError) as exc:
        return _render_reproduce_result(directory, [str(exc)], args.json)

    with source_reader:
        try:
            manifest_digest, _ = source_reader.digest(
                MANIFEST_FILENAME, max_bytes=MAX_CONTROL_FILE_BYTES
            )
            if manifest_digest != preflight.manifest_sha256:
                return _render_reproduce_result(
                    directory, ["dataset changed after preflight verification"], args.json
                )
            document = read_manifest(directory, reader=source_reader)
            expected_sums = {output["path"]: output["sha256"] for output in document["outputs"]}
            expected_sums[MANIFEST_FILENAME] = manifest_digest
            if source_reader.read_text(
                SUMS_FILENAME, max_bytes=MAX_CONTROL_FILE_BYTES
            ) != render_sums(expected_sums):
                return _render_reproduce_result(
                    directory, [f"{SUMS_FILENAME} changed after preflight verification"], args.json
                )
            expected_entries = set(expected_sums) | {SUMS_FILENAME}
            entries = source_reader.entries()
            if (
                any(entry.kind != "file" for entry in entries)
                or {entry.name for entry in entries} != expected_entries
            ):
                return _render_reproduce_result(
                    directory, ["dataset inventory changed after preflight verification"], args.json
                )
        except (DatasetIOError, OSError, ValueError) as exc:
            return _render_reproduce_result(directory, [str(exc)], args.json)

        pack_hint = document["pack"]["name"]
        pack_root = _locate_pack(directory, pack_hint)
        if pack_root is None:
            message = (
                f"cannot locate pack {pack_hint!r} to re-mint from. Pass a checkout of "
                "the pack at the version the manifest records."
            )
            if args.json:
                print(json.dumps({"ok": False, "problems": [message]}, indent=2))
            else:
                print(f"mintmark: {message}", file=sys.stderr)
            return EXIT_USAGE

        differences = []
        note: str | None = None
        with tempfile.TemporaryDirectory() as temporary:
            replica = Path(temporary) / "replica"
            mint(
                pack=pack_root,
                recipe=document["recipe"]["name"],
                seed=int(document["seed"]),
                out=replica,
                identifier_policy=document["identifier_policy"],
                fmt=_format_of(document),
                # Replay invocation overrides, not their resolved counts.
                records=document["recipe"]["parameters"].get("overrides", {}).get("records"),
                invocation="mintmark reproduce",
            )
            for output in document["outputs"]:
                name = output["path"]
                try:
                    original = source_reader.read_bytes(name, max_bytes=MAX_DATA_FILE_BYTES)
                except (DatasetIOError, OSError, ValueError) as exc:
                    differences.append(str(exc))
                    continue
                fresh_path = replica / name
                if not fresh_path.exists():
                    differences.append(f"{name}: the re-mint did not produce this file")
                    continue
                if original != fresh_path.read_bytes():
                    differences.append(f"{name}: bytes differ from the recorded mint")

            fresh_manifest = json.loads((replica / MANIFEST_FILENAME).read_text(encoding="utf-8"))
            drift = _manifest_drift(comparable(document), comparable(fresh_manifest))
            engine_version_path = ("mintmark", "engine_version")
            engine_only = set(drift) == {engine_version_path}
            if drift and not engine_only:
                differences.extend(
                    f"{MANIFEST_FILENAME}: {_display_path(path)}: {a!r} against {b!r}"
                    for path, (a, b) in sorted(drift.items())
                )
            if engine_only and not differences:
                recorded, running = drift[engine_version_path]
                note = (
                    f"data files are byte-identical, and were produced by engine "
                    f"{recorded} rather than the {running} running here. The determinism "
                    f"claim covers a fixed engine version, so this confirms the bytes "
                    f"rather than the claim."
                )

    return _render_reproduce_result(directory, differences, args.json, note=note)


def _render_reproduce_result(
    directory: Path, differences: list[str], as_json: bool, *, note: str | None = None
) -> int:
    payload: dict[str, Any] = {
        "ok": not differences,
        "directory": str(directory),
        "problems": differences,
    }
    if note is not None:
        payload["note"] = note
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif differences:
        for line in differences:
            print(f"MISMATCH: {line}", file=sys.stderr)
    elif note is not None:
        print("reproduce: byte-identical")
        print(f"NOTE: {note}")
    else:
        print("reproduce: byte-identical")
    return EXIT_OK if not differences else EXIT_REPRODUCE_MISMATCH


def _manifest_drift(
    recorded: dict[str, Any], fresh: dict[str, Any]
) -> dict[tuple[str, ...], tuple[Any, Any]]:
    """Every leaf that differs, keyed by an unambiguous path tuple.

    `differs outside the excluded provenance block` was true and useless: it told
    a consumer that something was wrong without telling them what, which is the
    shape of message people learn to ignore.
    """
    drift: dict[tuple[str, ...], tuple[Any, Any]] = {}

    def walk(left: Any, right: Any, path: tuple[str, ...]) -> None:
        if isinstance(left, dict) and isinstance(right, dict):
            for key in sorted(set(left) | set(right)):
                walk(left.get(key), right.get(key), (*path, key))
        elif left != right:
            drift[path] = (left, right)

    walk(recorded, fresh, ())
    return drift


def _display_path(path: tuple[str, ...]) -> str:
    return "/" + "/".join(part.replace("~", "~0").replace("/", "~1") for part in path)


def _format_of(document: dict[str, Any]) -> str:
    for output in document["outputs"]:
        if output["path"].endswith(".csv"):
            return "csv"
    return "jsonl"


def _locate_pack(directory: Path, name: str) -> Path | None:
    """Find the pack a manifest names, in the usual places.

    A dataset does not carry its pack, so reproduction needs one. Looking beside
    the dataset and in the working directory covers the two cases that matter:
    a developer re-minting their own run, and a consumer who cloned the pack.
    """
    candidates = [
        directory / "pack",
        directory.parent / name,
        Path.cwd() / name,
        Path.cwd() / "packs" / name.removeprefix("mintmark-"),
        Path.cwd(),
        # The engine ships the example pack, so a dataset minted from it can be
        # reproduced without cloning anything. Without this, the quickstart's own
        # output could not be reproduced by the tool that advertises reproduce as
        # the check that makes a manifest mean something.
        packaged_pack_dir(name.removeprefix("mintmark-")),
    ]
    for candidate in candidates:
        if (candidate / "pack.yaml").exists():
            try:
                if load_pack(candidate).name == name:
                    return candidate
            except PackError:
                continue
    return None


def _cmd_packcheck(args: argparse.Namespace) -> int:
    pack_root = resolve_pack(args.pack)
    loaded = load_pack(pack_root)

    problems: list[str] = []
    warnings: list[str] = []

    with tempfile.TemporaryDirectory() as temporary:
        for recipe_name, recipe in sorted(loaded.recipes.items()):
            out = Path(temporary) / f"mini-{recipe_name}"
            overrides = {name: min(25, count) for name, count in recipe.records.items()}
            try:
                mint(
                    pack=pack_root,
                    recipe=recipe_name,
                    seed=1,
                    out=out,
                    records=overrides,
                    invocation="mintmark packcheck",
                )
            except (MintError, ValueError) as error:
                problems.append(f"recipe {recipe_name}: mini-mint failed: {error}")
                continue

            report = verify(
                out,
                schema=_manifest_schema(),
                validators=_validators(),
                expected_taxonomy_pin=pin_digest(),
                known_labels=frozenset(label.value for label in Label),
            )
            problems.extend(f"recipe {recipe_name}: {p}" for p in report.problems)

            document = read_manifest(out)
            for stat in document["stats"]["coverage_targets"]:
                scaled = stat["target"] * 25
                if stat["achieved"] * max(1, sum(recipe.records.values())) < scaled:
                    warnings.append(
                        f"recipe {recipe_name}: coverage target {stat['label']}="
                        f"{stat['target']} may be infeasible at the declared counts"
                    )
            shutil.rmtree(out, ignore_errors=True)

    payload = {
        "pack": loaded.name,
        "version": loaded.version,
        "digest": loaded.digest,
        "ok": not problems,
        "recipes": sorted(loaded.recipes),
        "problems": problems,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"pack: {loaded.name} {loaded.version}")
        print(f"digest: {loaded.digest}")
        print(f"record types: {', '.join(t.type_name for t in loaded.record_types)}")
        print(f"recipes: {', '.join(sorted(loaded.recipes))}")
        for warning in warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
        for problem in problems:
            print(f"PROBLEM: {problem}", file=sys.stderr)
        print("packcheck: ok" if not problems else "packcheck: FAILED")
    return EXIT_OK if not problems else EXIT_INVALID_PACK


def _cmd_inspect(args: argparse.Namespace) -> int:
    loaded = load_pack(resolve_pack(args.pack))
    payload = {
        "name": loaded.name,
        "version": loaded.version,
        "requires_core": loaded.requires_core.text,
        "locale": loaded.locale,
        "allowed_identifier_policies": list(loaded.allowed_identifier_policies),
        "digest": loaded.digest,
        "record_types": [
            {
                "type_name": t.type_name,
                "id_prefix": t.id_prefix,
                "order": t.order,
                "fields": len(t.fields),
                "document_fields": [f.name for f in t.document_fields],
            }
            for t in loaded.record_types
        ],
        "recipes": sorted(loaded.recipes),
        "template_sets": sorted(loaded.template_sets),
        "lexicons": sorted(loaded.lexicons),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"{loaded.name} {loaded.version} (locale {loaded.locale})")
        print(f"requires core {loaded.requires_core.text}")
        print(f"policies: {', '.join(loaded.allowed_identifier_policies)}")
        print(f"digest: {loaded.digest}")
        for record_type in loaded.record_types:
            print(
                f"  {record_type.order}. {record_type.type_name} "
                f"[{record_type.id_prefix}] {len(record_type.fields)} fields"
            )
        print(f"recipes: {', '.join(sorted(loaded.recipes)) or 'none'}")
    return EXIT_OK


def _cmd_schema(args: argparse.Namespace) -> int:
    path = schema_dir() / f"{args.which}.schema.json"
    print(path.read_text(encoding="utf-8").rstrip("\n"))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
