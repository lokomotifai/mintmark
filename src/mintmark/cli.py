"""The command line surface, on argparse and the standard library only.

Seven verbs, five exit codes, one interruption code, and a stable `--json`
payload for each verb that declares one. Those are a public contract under
semantic versioning: adding a field is a minor version, removing or retyping one
is a major.

Exit codes carry meaning, because a script consuming this tool needs to tell a
malformed pack from a tampered dataset from a reproduction mismatch:

    0  success
    1  usage error
    2  invalid pack, failing closed
    3  verification failure
    4  reproduction mismatch

An interrupted run returns 130, the conventional code for a process stopped by
SIGINT, after the staging directory has been discarded.

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
from typing import Any, Never

from mintmark.annotate import Label, pin_digest
from mintmark.engine.templates import (
    Alternation,
    EntitySlot,
    FieldSlot,
    IdentifierSlot,
    LexiconSlot,
    Literal,
    Optional,
    TemplateError,
    parse_template,
)
from mintmark.identifiers import ALL_ENGINES, CHECKSUMMED
from mintmark.lexicons import load as load_denylist
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
from mintmark.manifest.safety import identifier_candidates, scalar_texts
from mintmark.minting import MintError, asset_dir, mint, packaged_pack_dir, resolve_pack, schema_dir
from mintmark.packs.loader import PackError
from mintmark.packs.model import load_pack

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_INVALID_PACK = 2
EXIT_VERIFY_FAILED = 3
EXIT_REPRODUCE_MISMATCH = 4
# 128 + SIGINT, the code a shell reports for a process the user stopped.
EXIT_INTERRUPTED = 130


def _validators() -> dict[str, Any]:
    """Compose the identifier validators verification needs.

    `manifest` sits above `identifiers` in the declared dependency direction, so
    it cannot import them. This is the layer that knows about both.
    """
    return {name: engine.is_checksum_valid for name, engine in CHECKSUMMED.items()}


def _shapes() -> dict[str, Any]:
    """Compose the per-label surface checks span verification applies.

    A span labeled IBAN must read like an IBAN. Checksums prove the file is the
    one the manifest sealed; this proves the offsets still point at the value
    the label names, which a consistent rewrite of every digest would not.
    """
    return {name: engine.is_well_formed for name, engine in ALL_ENGINES.items()}


def _manifest_schema() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(
        (schema_dir() / "manifest.schema.json").read_text(encoding="utf-8")
    )
    return document


class _Parser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; this tool's contract says 1.

    Two is what the contract reserves for a malformed pack, so a script that
    branches on the code must be able to trust the table in this module's
    docstring rather than argparse's own convention.
    """

    def error(self, message: str) -> Never:
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def build_parser() -> argparse.ArgumentParser:
    from mintmark import __version__

    parser = _Parser(
        prog="mintmark",
        description="Mint deterministic, fully synthetic, Turkish-first labeled datasets.",
    )
    parser.add_argument("--version", action="version", version=f"mintmark {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)

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
        default="safe",
        help="safe by default; validator requires an explicit caller opt-in",
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
    except (PackError, TemplateError) as error:
        # A malformed template is a malformed pack: it is a file the pack ships.
        return _fail(args, error, EXIT_INVALID_PACK)
    except MintError as error:
        return _fail(args, error, EXIT_USAGE)
    except (KeyError, ValueError) as error:
        return _fail(args, error, EXIT_USAGE)
    except FileNotFoundError as error:
        return _fail(args, error, EXIT_VERIFY_FAILED)
    except OSError as error:
        # An output directory that already exists, a parent that refuses writes,
        # a path that is a file: the invocation cannot be satisfied as given.
        return _fail(args, error, EXIT_USAGE)
    except KeyboardInterrupt:
        # The staging directory is already gone: staged_output discards it on
        # the way out. All that is left is to say so without a traceback.
        print("mintmark: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED

    return EXIT_USAGE


def _fail(args: argparse.Namespace, error: BaseException, code: int) -> int:
    """Report a failure the way the verb was asked to report: text, or JSON.

    A caller that passed --json is parsing stdout. Leaving it empty on the error
    path forces them to fall back to scraping stderr, which is the thing --json
    exists to make unnecessary.
    """
    message = str(error)
    print(f"mintmark: {message}", file=sys.stderr)
    if getattr(args, "json", False):
        print(json.dumps({"ok": False, "problems": [message]}, ensure_ascii=False, indent=2))
    return code


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
        shapes=_shapes(),
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
        shapes=_shapes(),
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
            searched = ", ".join(str(path) for path in _pack_candidates(directory, pack_hint))
            message = (
                f"cannot locate pack {pack_hint!r} to re-mint from. A dataset does not "
                f"carry its pack, so place a checkout of {pack_hint!r} at the version "
                f"the manifest records in one of the places searched, or run from inside "
                f"that checkout. Searched: {searched}"
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


def _pack_candidates(directory: Path, name: str) -> list[Path]:
    """The places a pack is looked for, in order, so an error can name them."""
    return [
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


def _locate_pack(directory: Path, name: str) -> Path | None:
    """Find the pack a manifest names, in the usual places.

    A dataset does not carry its pack, so reproduction needs one. Looking beside
    the dataset and in the working directory covers the two cases that matter:
    a developer re-minting their own run, and a consumer who cloned the pack.
    """
    for candidate in _pack_candidates(directory, name):
        if (candidate / "pack.yaml").exists():
            try:
                if load_pack(candidate).name == name:
                    return candidate
            except PackError:
                continue
    return None


MAX_TEMPLATE_SAFETY_EXPANSIONS = 10_000


def _literal_expansions(nodes: tuple[Any, ...]) -> tuple[str, ...]:
    """Enumerate every literal grammar branch under a strict cross-product cap."""
    outputs = [""]
    for node in nodes:
        variants: tuple[str, ...]
        match node:
            case Literal(text=text):
                variants = (text,)
            case FieldSlot() | EntitySlot() | IdentifierSlot() | LexiconSlot():
                variants = (" ",)
            case Alternation(branches=branches):
                variants = tuple(
                    rendering for branch in branches for rendering in _literal_expansions(branch)
                )
            case Optional(body=body):
                variants = ("", *_literal_expansions(body))
            case _:
                raise AssertionError(f"unknown template node {node!r}")
        if len(outputs) * len(variants) > MAX_TEMPLATE_SAFETY_EXPANSIONS:
            raise ValueError(
                f"template expands beyond {MAX_TEMPLATE_SAFETY_EXPANSIONS} safety branches"
            )
        outputs = [prefix + suffix for prefix in outputs for suffix in variants]
    return tuple(outputs)


def _pack_safety(pack_root: Path, loaded: Any) -> tuple[Any, list[str]]:
    """Exhaustively inspect declaration-controlled emitted strings."""
    core = load_denylist(asset_dir("denylist") / "institutions-tr.txt")
    extension_path = pack_root / "lexicons" / "denylist_extension.txt"
    matcher = load_denylist(extension_path) if extension_path.exists() else core
    problems: list[str] = []
    if not matcher.covers(core):
        missing = sorted(matcher.missing_from(core))[:5]
        problems.append(f"denylist extension omits core entries: {missing}")

    surfaces: list[tuple[str, str]] = []
    for name, values in loaded.lexicons.items():
        surfaces.extend((f"lexicon {name}", value) for value in values)
    for record_type in loaded.record_types:
        for field in record_type.fields:
            source = f"field {record_type.type_name}.{field.name}"
            if field.generator_kind == "literal":
                surfaces.append((source, field.generator_argument))
            surfaces.extend((source, text) for text in scalar_texts(field.params))
    for set_name, entries in loaded.template_sets.items():
        for entry in entries:
            try:
                nodes = parse_template(
                    entry.text,
                    template_id=entry.id,
                    known_labels=frozenset(label.value for label in Label),
                    known_identifiers=frozenset(ALL_ENGINES),
                    known_lexicons=frozenset(loaded.lexicons),
                )
            except TemplateError as exc:
                problems.append(f"template {set_name}/{entry.id}: {exc.rule}: {exc.detail}")
                continue
            try:
                renderings = _literal_expansions(nodes)
            except ValueError as exc:
                problems.append(f"template {set_name}/{entry.id}: {exc}")
                continue
            surfaces.extend((f"template {set_name}/{entry.id}", text) for text in renderings)

    for source, surface in surfaces:
        for hit in matcher.scan(surface):
            problems.append(f"{source}: {hit.render()}")
        for candidate in identifier_candidates(surface):
            valid_as = [
                name for name, engine in CHECKSUMMED.items() if engine.is_checksum_valid(candidate)
            ]
            if valid_as:
                problems.append(
                    f"{source}: checksum-valid {'/'.join(valid_as)} literal {candidate!r} "
                    "is forbidden by safe policy"
                )
    return matcher, problems


def _mini_record_counts(loaded: Any, recipe: Any) -> dict[str, int]:
    """Shrink a valid recipe while retaining every relationship bound."""
    selected = {name: min(25, count) for name, count in recipe.records.items()}
    for record_type in loaded.record_types:
        for field in record_type.fields:
            if field.ref is None:
                continue
            if selected.get(record_type.type_name, 0) == 0:
                continue
            parents = selected.get(field.ref.parent, 0)
            low = parents * min(field.ref.counts)
            high = parents * max(field.ref.counts)
            selected[record_type.type_name] = min(
                max(selected.get(record_type.type_name, 0), low), high
            )
    return selected


def _cmd_packcheck(args: argparse.Namespace) -> int:
    pack_root = resolve_pack(args.pack)
    loaded = load_pack(pack_root)

    problems: list[str] = []
    warnings: list[str] = []
    matcher, safety_problems = _pack_safety(pack_root, loaded)
    problems.extend(safety_problems)

    with tempfile.TemporaryDirectory() as temporary:
        for recipe_name, recipe in sorted(loaded.recipes.items()):
            out = Path(temporary) / f"mini-{recipe_name}"
            overrides = _mini_record_counts(loaded, recipe)
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
                shapes=_shapes(),
                expected_taxonomy_pin=pin_digest(),
                known_labels=frozenset(label.value for label in Label),
            )
            problems.extend(f"recipe {recipe_name}: {p}" for p in report.problems)

            document = read_manifest(out)
            for output in document["outputs"]:
                output_path = out / output["path"]
                for hit in matcher.scan(output_path.read_text(encoding="utf-8")):
                    problems.append(f"recipe {recipe_name}: {output['path']}: {hit.render()}")
            for stat in document["stats"]["coverage_targets"]:
                scaled_target = stat["target"] * max(1, sum(overrides.values()))
                if stat["achieved"] * max(1, sum(recipe.records.values())) < scaled_target:
                    problems.append(
                        f"recipe {recipe_name}: coverage target {stat['label']}="
                        f"{stat['target']} is infeasible at the declared counts"
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
