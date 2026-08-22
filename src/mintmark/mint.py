"""The mint pipeline: pack plus recipe plus seed into a sealed dataset.

This module is where the layers meet. Everything below it is deliberately
unaware of everything beside it: `engine` knows nothing of taxonomies, `packs`
knows nothing of identifiers, `manifest` knows nothing of how a value was drawn.
Composition happens once, here, which is what keeps those boundaries honest.

The shape of a mint:

    load and cross-validate the pack
    for each record type, in declared order:
        generate records, assigning references from parent indices
        render document fields, recording spans as they are placed
    write data files and sidecars into a staging directory
    seal with a manifest and checksums
    move the staging directory into place

Nothing is visible at the target path until the seal is complete, so an
interrupted mint leaves no directory that looks like a dataset.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mintmark.annotate import (
    Label,
    Resolvers,
    SidecarRecord,
    Span,
    parse_label,
    pin,
    pin_digest,
    render,
    write_sidecar,
)
from mintmark.emit import csv_header, render_csv_row, render_record, staged_output
from mintmark.engine.draws import boolean, bounded, bounded_range, datetime_in_window
from mintmark.engine.prng import SplitMix64
from mintmark.engine.records import (
    DistributionTally,
    Record,
    assign_children,
    entity_id,
)
from mintmark.engine.streams import StreamFactory
from mintmark.engine.tables import Table, load_table
from mintmark.engine.templates import Alternation, FieldSlot, Node, Optional, parse_template
from mintmark.identifiers import (
    ALL_ENGINES,
    CHECKSUMMED,
    IdentifierPolicy,
    email,
    pan,
    parse_policy,
)
from mintmark.lexicons import load as load_denylist
from mintmark.manifest import (
    MANIFEST_FILENAME,
    SUMS_FILENAME,
    CoverageStat,
    DistributionStat,
    Manifest,
    OutputFile,
    file_digest,
    render_sums,
)
from mintmark.manifest.document import SUPPORTED_PLATFORMS
from mintmark.manifest.safety import identifier_candidates
from mintmark.packs.model import (
    Field,
    Pack,
    Recipe,
    RecordType,
    load_pack,
    record_count_problem,
)

ENGINE_MAJOR = 0
TURKEY_OFFSET = "+03:00"

KNOWN_IDENTIFIERS = frozenset(ALL_ENGINES)
KNOWN_LABELS = frozenset(label.value for label in Label)


def _data_root() -> Path:
    packaged = Path(__file__).resolve().parent / "_data"
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[2]


def asset_dir(name: str) -> Path:
    return _data_root() / "assets" / name


def schema_dir() -> Path:
    return _data_root() / "schemas"


def packaged_pack_dir(name: str) -> Path:
    return _data_root() / "packs" / name


def resolve_pack(argument: str) -> Path:
    """A path, unless it names a pack that ships inside the distribution.

    The example pack is in the wheel so the quickstart works without cloning
    anything, which is the whole reason it is shipped. Until this existed there
    was no way to point at it: `--pack packs/example` is a path that only exists
    in a checkout, so somebody who installed from an index followed the README
    into an error.

    A local path always wins. `example` resolves to the packaged pack only when
    nothing of that name sits in the working directory, so this can never
    shadow a real directory or quietly rescue a typo in a longer path.
    """
    candidate = Path(argument)
    if candidate.exists():
        return candidate
    packaged = packaged_pack_dir(argument)
    if (packaged / "pack.yaml").exists():
        return packaged
    return candidate


@dataclass(slots=True)
class MintSummary:
    """What a mint produced, mirroring the CLI's --json payload."""

    out: str
    pack: str
    pack_version: str
    pack_digest: str
    recipe: str
    seed: int
    identifier_policy: str
    fmt: str
    record_counts: dict[str, int] = dataclass_field(default_factory=dict)
    entity_coverage: dict[str, int] = dataclass_field(default_factory=dict)
    outputs: list[str] = dataclass_field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "out": self.out,
            "pack": self.pack,
            "pack_version": self.pack_version,
            "pack_digest": self.pack_digest,
            "recipe": self.recipe,
            "seed": str(self.seed),
            "identifier_policy": self.identifier_policy,
            "format": self.fmt,
            "record_counts": dict(sorted(self.record_counts.items())),
            "entity_coverage": dict(sorted(self.entity_coverage.items())),
            "outputs": sorted(self.outputs),
        }


class MintError(RuntimeError):
    """A mint cannot proceed. Distinct from a malformed pack, which exits 2."""


def attribution_line(pack: Pack, recipe: str, seed: int) -> str:
    """The credit line a consumer reproduces to satisfy the dataset license.

    Written into every manifest whatever the license says, because somebody who
    wants to credit the source should not have to assemble the string from four
    other fields and guess at the format. It names the dataset uniquely: two runs
    that differ in recipe or seed are different datasets and get different lines.
    """
    return (
        f"{pack.name} {pack.version} reference dataset "
        f"(recipe {recipe}, seed {seed}), lokomotifai, "
        f"licensed {pack.dataset_license}"
    )


def mint(
    *,
    pack: str | Path,
    recipe: str,
    seed: int,
    out: str | Path,
    identifier_policy: str = "safe",
    fmt: str = "jsonl",
    records: dict[str, int] | None = None,
    invocation: str = "mintmark mint",
) -> MintSummary:
    """Mint one dataset. Byte-identical for identical inputs."""
    pack_root = Path(pack)
    target = Path(out)
    policy = parse_policy(identifier_policy)

    loaded = load_pack(pack_root)
    if policy.value not in loaded.allowed_identifier_policies:
        allowed = ", ".join(loaded.allowed_identifier_policies)
        raise MintError(f"this pack allows identifier policies [{allowed}], not {policy.value!r}")

    declared = loaded.recipe(recipe)
    counts = dict(declared.records)
    overrides: dict[str, Any] = {}
    if records:
        for type_name, count in records.items():
            if type_name not in counts:
                raise MintError(
                    f"--records names {type_name!r}, which recipe {recipe!r} does not declare"
                )
            counts[type_name] = count
        overrides["records"] = dict(sorted(records.items()))
    count_problem = record_count_problem(counts)
    if count_problem is not None:
        rule, detail = count_problem
        raise MintError(f"{rule}: {detail}")

    factory = StreamFactory(
        seed=seed,
        engine_major=ENGINE_MAJOR,
        pack_name=loaded.name,
        pack_version=loaded.version,
        recipe_name=declared.name,
    )
    context = _MintContext(
        pack=loaded, recipe=declared, factory=factory, policy=policy, counts=counts
    )
    context.compile_templates()

    generated: dict[str, list[Record]] = {}
    sidecars: dict[str, list[SidecarRecord]] = {}
    for record_type in loaded.record_types:
        rows, docs = context.generate_type(record_type, generated)
        generated[record_type.type_name] = rows
        if docs:
            sidecars[record_type.type_name] = docs

    if policy is IdentifierPolicy.SAFE:
        _assert_safe_records(generated)

    return _write(
        target=target,
        loaded=loaded,
        declared=declared,
        seed=seed,
        policy=policy,
        fmt=fmt,
        generated=generated,
        sidecars=sidecars,
        context=context,
        overrides=overrides,
        invocation=invocation,
    )


@dataclass(slots=True)
class _MintContext:
    """Per-mint state: tallies, caches, and the resolvers a render needs."""

    pack: Pack
    recipe: Recipe
    factory: StreamFactory
    policy: IdentifierPolicy
    counts: dict[str, int]
    tallies: dict[str, DistributionTally] = dataclass_field(default_factory=dict)
    coverage: dict[str, int] = dataclass_field(default_factory=dict)
    _tables: dict[str, Table] = dataclass_field(default_factory=dict)
    _templates: dict[str, tuple[tuple[Node, ...], ...]] = dataclass_field(default_factory=dict)

    def compile_templates(self) -> None:
        """Compile every declared template before any records are generated."""
        for set_name in sorted(self.pack.template_sets):
            self.templates(set_name)
        for record_type in self.pack.record_types:
            allowed = {f"{record_type.type_name}.{field.name}" for field in record_type.fields}
            for document_field in record_type.document_fields:
                for entry in self._templates[document_field.generator_argument]:
                    for path in _field_slot_paths(entry):
                        if path not in allowed:
                            raise MintError(
                                f"template set {document_field.generator_argument!r} references "
                                f"unknown field {path!r} for record type {record_type.type_name!r}"
                            )

    def table(self, name: str) -> Table:
        if name not in self._tables:
            self._tables[name] = load_table(asset_dir("tables"), name)
        return self._tables[name]

    def templates(self, set_name: str) -> tuple[tuple[Node, ...], ...]:
        if set_name not in self._templates:
            entries = self.pack.template_sets[set_name]
            self._templates[set_name] = tuple(
                parse_template(
                    entry.text,
                    template_id=entry.id,
                    known_labels=KNOWN_LABELS,
                    known_identifiers=KNOWN_IDENTIFIERS,
                )
                for entry in entries
            )
        return self._templates[set_name]

    def lexicon_values(self, name: str) -> Sequence[str]:
        if name in self.pack.lexicons:
            return self.pack.lexicons[name]
        return core_lexicon(name)

    def generate_type(
        self, record_type: RecordType, generated: dict[str, list[Record]]
    ) -> tuple[list[Record], list[SidecarRecord]]:
        count = self.counts.get(record_type.type_name, 0)
        assignments = self._reference_assignments(record_type, generated, count)

        rows: list[Record] = []
        documents: list[SidecarRecord] = []
        for index in range(count):
            row: Record = {}
            graph = {record_type.type_name: row}
            for declared in record_type.fields:
                value = self._field_value(record_type, declared, index, row, assignments, generated)
                row[declared.name] = value

            doc_fields = record_type.document_fields
            if doc_fields:
                text, spans = self._render_document(record_type, index, row, graph)
                row[doc_fields[0].name] = text
                documents.append(
                    SidecarRecord(
                        doc_id=str(row[record_type.fields[0].name]),
                        text=text,
                        spans=tuple(spans),
                    )
                )
                for span in spans:
                    self.coverage[span.label.value] = self.coverage.get(span.label.value, 0) + 1
            rows.append(row)
        return rows, documents

    def _reference_assignments(
        self, record_type: RecordType, generated: dict[str, list[Record]], count: int
    ) -> dict[str, list[int]]:
        assignments: dict[str, list[int]] = {}
        for declared in record_type.fields:
            if declared.type != "ref" or declared.ref is None:
                continue
            parents = generated.get(declared.ref.parent, [])
            assignments[declared.name] = assign_children(
                self.factory,
                site=f"{record_type.type_name}/{declared.name}",
                parent_count=len(parents),
                child_count=count,
                counts=declared.ref.counts,
                weights=declared.ref.weights,
            )
        return assignments

    def _field_value(
        self,
        record_type: RecordType,
        declared: Field,
        index: int,
        row: Record,
        assignments: dict[str, list[int]],
        generated: dict[str, list[Record]],
    ) -> Any:
        site = f"{record_type.type_name}/{index}/{declared.name}"
        stream = self.factory.stream(site)

        if declared.nullable and declared.null_rate and boolean(stream, declared.null_rate):
            return None

        kind = declared.generator_kind
        argument = declared.generator_argument
        params = declared.params

        # The reference check comes first. A ref field still declares a
        # generator, because the schema requires one, and dispatching on the
        # generator instead of the type made every reference resolve to the
        # child's own identifier: well formed, and pointing at the wrong record.
        if declared.type == "ref":
            parents = generated[declared.ref.parent]  # type: ignore[union-attr]
            parent_index = assignments[declared.name][index]
            parent_type = self.pack.record_type(declared.ref.parent)  # type: ignore[union-attr]
            return parents[parent_index][parent_type.fields[0].name]

        if kind == "seq_id":
            return entity_id(record_type.id_prefix, index)

        if kind == "identifier":
            return self._identifier(argument, stream, row)

        if kind == "lexicon":
            values = self.lexicon_values(argument)
            if not values:
                raise MintError(f"{site}: lexicon {argument!r} is empty")
            return values[bounded(stream, len(values))]

        if kind == "enum_weighted":
            options = [str(v) for v in params.get("values", [])]
            weights = [str(w) for w in params.get("weights", [])]
            tally = self.tallies.setdefault(
                f"{record_type.type_name}/{declared.name}",
                DistributionTally(
                    site=f"{record_type.type_name}/{declared.name}",
                    targets=dict(zip(options, weights, strict=True)),
                ),
            )
            from mintmark.engine.draws import weighted_index

            value = options[weighted_index(stream, weights)]
            tally.observe(value)
            return value

        if kind == "int_uniform":
            return bounded_range(stream, int(params.get("low", 0)), int(params.get("high", 1)))

        if kind == "int_lognormal_table":
            from mintmark.engine.tables import sample

            return sample(stream, self.table(argument))

        if kind == "datetime_window":
            return self._timestamp(stream, declared)

        if kind == "derived":
            return self._derived(argument, declared, stream, row)

        if kind == "grammar":
            return ""  # rendered after the row is complete

        raise MintError(f"{site}: no generator for {declared.generator!r}")

    def _identifier(self, name: str, stream: SplitMix64, row: Record) -> str:
        engine = ALL_ENGINES[name]
        if name == "EMAIL":
            return email.generate(
                stream,
                self.policy,
                first_name=str(row.get("first_name", "")),
                last_name=str(row.get("last_name", "")),
            )
        value = engine.generate(stream, self.policy)
        if name == "PAN":
            return pan.mask(value)
        return str(value)

    # A year of 365 days plus one leap day every four. The exact Gregorian rule
    # would be more accurate over centuries and is not worth a float here: this
    # positions a birth window, and being a day out at the edge of a forty-year
    # span changes nothing a consumer can observe.
    _DAYS_PER_YEAR = 365
    _SECONDS_PER_DAY = 86_400

    def _timestamp(self, stream: SplitMix64, declared: Field) -> str:
        start, end = self._field_window(declared)
        seconds = datetime_in_window(stream, start, end)
        moment = datetime.fromtimestamp(seconds, tz=UTC) + timedelta(hours=3)
        if declared.type == "date":
            return moment.date().isoformat()
        return moment.replace(tzinfo=None).isoformat() + TURKEY_OFFSET

    def _field_window(self, declared: Field) -> tuple[int, int]:
        """The recipe window, unless the field asks to sit a whole age behind it.

        A birth date drawn from the recipe window puts every person's year of
        birth inside the year the records describe, which is visibly wrong on the
        first line a reader opens. `age_years: [low, high]` moves the draw to the
        span that would give a person that age at the start of the window.

        The default is the recipe window unchanged, so a field that says nothing
        keeps the behaviour every existing pack was built against.
        """
        window = self.recipe.date_window
        span = declared.params.get("age_years")
        if span is None:
            return window.start_epoch, window.end_epoch
        low, high = int(span[0]), int(span[1])
        return (
            window.start_epoch - self._age_seconds(high),
            window.start_epoch - self._age_seconds(low),
        )

    def _age_seconds(self, years: int) -> int:
        days = years * self._DAYS_PER_YEAR + years // 4
        return days * self._SECONDS_PER_DAY

    def _derived(self, rule: str, declared: Field, stream: SplitMix64, row: Record) -> Any:
        if rule == "email_from_name":
            return email.generate(
                stream,
                self.policy,
                first_name=str(row.get("first_name", "")),
                last_name=str(row.get("last_name", "")),
                subdomain=str(declared.params.get("subdomain") or "") or None,
            )
        if rule == "flag_unless":
            # Turns a sentinel enum value into a boolean, so a row can carry both
            # "which anomaly" and "is it anomalous" without two independent draws
            # that could disagree with each other.
            source = row.get(str(declared.params.get("source", "")))
            return source != declared.params.get("value")

        if rule == "copy_of":
            return row.get(str(declared.params.get("source", "")))
        if rule == "ratio_of":
            source = row.get(str(declared.params.get("source", "")))
            numerator = int(declared.params.get("numerator", 1))
            denominator = int(declared.params.get("denominator", 1))
            if not isinstance(source, int):
                return None
            return source * numerator // denominator
        if rule == "date_offset":
            source = row.get(str(declared.params.get("source", "")))
            days = int(declared.params.get("days", 0))
            if not isinstance(source, str):
                return None
            return (datetime.fromisoformat(source) + timedelta(days=days)).date().isoformat()
        raise MintError(f"unknown derived rule {rule!r}")

    def _render_document(
        self, record_type: RecordType, index: int, row: Record, graph: dict[str, Record]
    ) -> tuple[str, list[Span]]:
        doc_field = record_type.document_fields[0]
        set_name = doc_field.generator_argument
        templates = self.templates(set_name)
        stream = self.factory.stream(f"{record_type.type_name}/{index}/{doc_field.name}/pick")
        nodes = templates[bounded(stream, len(templates))]

        render_stream = self.factory.stream(
            f"{record_type.type_name}/{index}/{doc_field.name}/render"
        )
        labels = {
            f"{record_type.type_name}.{f.name}": parse_label(f.pii_label)
            for f in record_type.fields
            if f.pii_label != "none"
        }
        resolvers = Resolvers(
            field=lambda path: _resolve(graph, path),
            entity=lambda label, s: self._descriptor(label, s),
            identifier=lambda kind, s: self._identifier(kind, s, row),
            field_label=labels.get,
        )
        return render(
            nodes,
            stream=render_stream,
            resolvers=resolvers,
            special_rate=self.recipe.special_rate,
        )

    def _descriptor(self, label: Label, stream: SplitMix64) -> str:
        values = core_descriptors(label)
        return values[bounded(stream, len(values))]


def _resolve(graph: dict[str, Record], path: str) -> Any:
    head, _, tail = path.partition(".")
    record = graph.get(head)
    if record is None or not tail or tail not in record:
        raise MintError(f"template field slot {path!r} is not present in the record graph")
    return record[tail]


def _field_slot_paths(nodes: tuple[Node, ...]) -> Sequence[str]:
    paths: list[str] = []
    for node in nodes:
        if isinstance(node, FieldSlot):
            paths.append(node.path)
        elif isinstance(node, Alternation):
            for branch in node.branches:
                paths.extend(_field_slot_paths(branch))
        elif isinstance(node, Optional):
            paths.extend(_field_slot_paths(node.body))
    return paths


def _assert_safe_records(generated: dict[str, list[Record]]) -> None:
    """Prove the safe-policy claim against final values, regardless of their source."""
    for type_name, rows in generated.items():
        for index, row in enumerate(rows):
            for candidate in identifier_candidates(row):
                for identifier_name, engine in CHECKSUMMED.items():
                    if engine.is_checksum_valid(candidate):
                        raise MintError(
                            f"safe-policy invariant failed at {type_name} record {index}: "
                            f"output contains a checksum-valid {identifier_name}"
                        )


_CORE_LEXICON_CACHE: dict[str, list[str]] = {}


def core_lexicon(name: str) -> list[str]:
    """Load a lexicon the core ships, by name."""
    if name in _CORE_LEXICON_CACHE:
        return _CORE_LEXICON_CACHE[name]

    import yaml

    path = Path(__file__).resolve().parent / "lexicons" / "data" / f"{name}.yaml"
    if not path.exists():
        raise MintError(f"no core lexicon named {name!r}")
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    values = document.get("values", [])
    if values and isinstance(values[0], dict):
        values = [entry.get("name", "") for entry in values]
    result = [str(v) for v in values]
    _CORE_LEXICON_CACHE[name] = result
    return result


_DESCRIPTOR_CACHE: dict[str, list[str]] = {}


def _load_descriptors() -> dict[str, list[str]]:
    """Read the curated descriptor lexicon once.

    These live in a reviewed YAML file rather than in this module, because every
    sector pack's evaluation recipe draws at least 300 spans per label and a
    handful of hard-coded strings would meet that count while producing a dataset
    that repeats itself. A detector scored on that is scored on memorization.
    """
    if _DESCRIPTOR_CACHE:
        return _DESCRIPTOR_CACHE

    import yaml

    path = Path(__file__).resolve().parent / "lexicons" / "data" / "special_descriptors.yaml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    for label, entry in document["labels"].items():
        _DESCRIPTOR_CACHE[label] = [str(v) for v in entry["values"]]
    return _DESCRIPTOR_CACHE


def core_descriptors(label: Label) -> list[str]:
    values = _load_descriptors().get(label.value)
    if not values:
        raise MintError(
            f"no descriptor lexicon for {label.value}; a template may not draw an "
            "entity of a label the core has no curated surfaces for"
        )
    return values


def _write(
    *,
    target: Path,
    loaded: Pack,
    declared: Recipe,
    seed: int,
    policy: IdentifierPolicy,
    fmt: str,
    generated: dict[str, list[Record]],
    sidecars: dict[str, list[SidecarRecord]],
    context: _MintContext,
    overrides: dict[str, Any],
    invocation: str,
) -> MintSummary:
    if fmt not in {"jsonl", "csv"}:
        raise MintError(f"unknown format {fmt!r}; expected jsonl or csv")

    summary = MintSummary(
        out=str(target),
        pack=loaded.name,
        pack_version=loaded.version,
        pack_digest=loaded.digest,
        recipe=declared.name,
        seed=seed,
        identifier_policy=policy.value,
        fmt=fmt,
    )

    with staged_output(target) as staged:
        for record_type in loaded.record_types:
            rows = generated.get(record_type.type_name, [])
            order = tuple(f.name for f in record_type.fields)
            name = f"{record_type.type_name}.{fmt}"
            with staged.open(name) as handle:
                if fmt == "csv":
                    handle.write(csv_header(order))
                    for row in rows:
                        handle.write(render_csv_row(row, order))
                else:
                    for row in rows:
                        handle.write(render_record(row, order) + "\n")
            summary.outputs.append(name)
            summary.record_counts[record_type.type_name] = len(rows)

            if record_type.type_name in sidecars:
                sidecar_name = f"{record_type.type_name}.labels.jsonl"
                with staged.open(sidecar_name) as handle:
                    write_sidecar(handle, sidecars[record_type.type_name])
                summary.outputs.append(sidecar_name)

        outputs = tuple(
            OutputFile(
                path=name,
                bytes=(staged.path / name).stat().st_size,
                sha256=file_digest(staged.path / name),
                records=summary.record_counts.get(name.split(".")[0], 0)
                if not name.endswith(".labels.jsonl")
                else len(sidecars.get(name.split(".")[0], [])),
            )
            for name in sorted(summary.outputs)
        )

        summary.entity_coverage = dict(context.coverage)
        manifest = Manifest(
            engine_version=_engine_version(),
            pack_name=loaded.name,
            pack_version=loaded.version,
            pack_digest=loaded.digest,
            recipe_name=declared.name,
            records=dict(summary.record_counts),
            date_window=(
                declared.date_window.start.isoformat(),
                declared.date_window.end.isoformat(),
            ),
            seed=seed,
            identifier_policy=policy.value,
            dataset_license=loaded.dataset_license,
            attribution=attribution_line(loaded, declared.name, seed),
            taxonomy=pin(),
            outputs=outputs,
            distributions=tuple(
                DistributionStat(
                    site=tally.site,
                    target=tally.targets,
                    achieved=tally.achieved(),
                    within_tolerance=tally.within_tolerance(),
                )
                for tally in context.tallies.values()
            ),
            coverage=tuple(
                CoverageStat(
                    label=label,
                    target=target_count,
                    achieved=context.coverage.get(label, 0),
                )
                for label, target_count in sorted(declared.coverage_targets.items())
            ),
            entity_coverage=dict(context.coverage),
            created_utc=datetime.now(tz=UTC).isoformat(timespec="seconds"),
            invocation=invocation,
            overrides=overrides,
        )
        with staged.open(MANIFEST_FILENAME) as handle:
            handle.write(manifest.render())

        sums = {output.path: output.sha256 for output in outputs}
        sums[MANIFEST_FILENAME] = file_digest(staged.path / MANIFEST_FILENAME)
        with staged.open(SUMS_FILENAME) as handle:
            handle.write(render_sums(sums))

    return summary


def _engine_version() -> str:
    from mintmark import __version__

    return __version__


def taxonomy_pin() -> str:
    return pin_digest()


def supported_platforms() -> tuple[str, ...]:
    return SUPPORTED_PLATFORMS


def denylist() -> Any:
    return load_denylist(asset_dir("denylist") / "institutions-tr.txt")
