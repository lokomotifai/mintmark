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
from mintmark.engine.templates import Node, parse_template
from mintmark.identifiers import ALL_ENGINES, IdentifierPolicy, email, pan, parse_policy
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
from mintmark.packs.model import Field, Pack, Recipe, RecordType, load_pack

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

    generated: dict[str, list[Record]] = {}
    sidecars: dict[str, list[SidecarRecord]] = {}
    for record_type in loaded.record_types:
        rows, docs = context.generate_type(record_type, generated)
        generated[record_type.type_name] = rows
        if docs:
            sidecars[record_type.type_name] = docs

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

    def lexicon_values(self, name: str) -> list[str]:
        if name in self.pack.lexicons:
            values = self.pack.lexicons[name].get("values", [])
            return [str(v) for v in values]
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

    def _timestamp(self, stream: SplitMix64, declared: Field) -> str:
        window = self.recipe.date_window
        seconds = datetime_in_window(stream, window.start_epoch, window.end_epoch)
        moment = datetime.fromtimestamp(seconds, tz=UTC) + timedelta(hours=3)
        if declared.type == "date":
            return moment.date().isoformat()
        return moment.replace(tzinfo=None).isoformat() + TURKEY_OFFSET

    def _derived(self, rule: str, declared: Field, stream: SplitMix64, row: Record) -> Any:
        if rule == "email_from_name":
            return email.generate(
                stream,
                self.policy,
                first_name=str(row.get("first_name", "")),
                last_name=str(row.get("last_name", "")),
                subdomain=str(declared.params.get("subdomain") or "") or None,
            )
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
        return render(nodes, stream=render_stream, resolvers=resolvers)

    def _descriptor(self, label: Label, stream: SplitMix64) -> str:
        values = core_descriptors(label)
        return values[bounded(stream, len(values))]


def _resolve(graph: dict[str, Record], path: str) -> Any:
    head, _, tail = path.partition(".")
    record = graph.get(head)
    if record is None:
        return None
    return record.get(tail)


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


# Neutral-register descriptors for the special-category labels. Curated, brief,
# and at category granularity: a class of thing, never a clinical detail, never
# an accusation, never attached to a real organization.
_DESCRIPTORS: dict[str, list[str]] = {
    "HEALTH": ["kronik rahatsizlik", "gecici is goremezlik", "rutin kontrol", "istirahat raporu"],
    "RELIGION": ["dini bayram izni", "inanc gerekçesiyle izin"],
    "ETHNICITY": ["etnik koken beyani", "anadil tercihi"],
    "POLITICAL": ["Yurttas Hareketi", "Ortak Gelecek Partisi"],
    "SEXUAL_LIFE": ["ozel yasam beyani"],
    "CRIMINAL": ["adli sicil kaydi sorgusu", "referans kontrolu"],
    "BIOMETRIC_REF": ["parmak izi ile mesai kaydi", "yuz tanima ile giris"],
    "UNION": ["Dayanisma Sendikasi", "Birlik Is Sendikasi", "Emek Sendikasi"],
    "PERSON": ["Mehmet Demir", "Ayse Kaya", "Ali Yildiz"],
    "ORG": ["Anka Lojistik", "Meridyen Teknoloji", "Toros Ticaret"],
    "ADDRESS": ["Cumhuriyet Mahallesi", "Zafer Sokak"],
    "DOB": ["1985-04-12", "1979-11-03"],
}


def core_descriptors(label: Label) -> list[str]:
    values = _DESCRIPTORS.get(label.value)
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
