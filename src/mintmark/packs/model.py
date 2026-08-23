"""Loading a whole pack directory into frozen, cross-validated declarations.

Schema validation catches a malformed file. It cannot catch a well-formed file
that refers to something absent: a field pointing at a parent record type nobody
declared, a generator naming a lexicon that does not exist, two record types
claiming the same position in the generation order. Those are the faults that
survive review, because each file reads correctly on its own.

So loading is two stages. Every file is validated against the schema, then the
assembled pack is cross-validated as a whole. Both stages fail closed, and every
message names the file, the location, and the rule.

Label closure is enforced by the schema's own enum rather than by importing the
taxonomy, which would put an edge from `packs` to `annotate` that the declared
dependency direction does not contain. A test asserts the schema enum and the
taxonomy enum stay identical, so the two cannot drift apart silently.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import jsonschema

from mintmark.engine.draws import TWO64
from mintmark.engine.version import VERSION
from mintmark.packs.digest import PackDigestError, pack_digest
from mintmark.packs.loader import PackError, load_yaml
from mintmark.packs.semver import CoreRange, parse_range

SCHEMA_FILENAME = "pack.schema.json"
MAX_DECIMAL_PLACES = 19
MAX_DECLARATION_FILES = 1_024
MAX_RECORD_TYPES = 128
MAX_RECIPES = 128
# Calibrated above the largest declaration this pack family publishes, not below
# it. At 50_000 and 100_000 these refused mintmark-banking's 250_000 transactions
# and mintmark-hr's 72_000 payroll entries, which are the shapes those packs
# exist to produce. A bound that refuses the project's own reference datasets
# stops nothing an attacker wanted and stops the product.
MAX_RECORDS_PER_TYPE = 1_000_000
MAX_TOTAL_RECORDS = 2_000_000
MAX_TEMPLATE_ENTRIES_PER_SET = 4_096
MAX_LEXICON_ITEMS = 100_000
MAX_LEXICON_VALUE_CHARS = 4_096


def _schema_root() -> Path:
    """Where the shipped schemas live, in a source tree or an installed wheel."""
    packaged = Path(__file__).resolve().parent.parent / "_data" / "schemas"
    if packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[3] / "schemas"


def _load_schema() -> dict[str, Any]:
    path = _schema_root() / SCHEMA_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"pack schema not found at {path}")
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


SCHEMA: dict[str, Any] = _load_schema()


@dataclass(frozen=True, slots=True)
class RefSpec:
    """A child-to-parent reference with its per-parent count distribution."""

    parent: str
    counts: tuple[int, ...]
    weights: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Field:
    """One declared field. Serialization order is declaration order."""

    name: str
    type: str
    generator: str
    pii_label: str
    params: dict[str, Any] = dataclass_field(default_factory=dict)
    ref: RefSpec | None = None
    nullable: bool = False
    null_rate: str | None = None

    @property
    def generator_kind(self) -> str:
        return self.generator.split(":", 1)[0]

    @property
    def generator_argument(self) -> str:
        _, _, argument = self.generator.partition(":")
        return argument


@dataclass(frozen=True, slots=True)
class RecordType:
    """One record type, its identifier prefix, and its place in the order."""

    type_name: str
    id_prefix: str
    order: int
    fields: tuple[Field, ...]

    @property
    def document_fields(self) -> tuple[Field, ...]:
        return tuple(f for f in self.fields if f.type == "doc")


@dataclass(frozen=True, slots=True)
class DateWindow:
    """The virtual clock's bounds, as UTC instants."""

    start: datetime
    end: datetime

    @property
    def start_epoch(self) -> int:
        return int(self.start.timestamp())

    @property
    def end_epoch(self) -> int:
        return int(self.end.timestamp())


@dataclass(frozen=True, slots=True)
class Recipe:
    """A named scenario: counts, window, document mix, and rates."""

    name: str
    records: dict[str, int]
    date_window: DateWindow
    special_rate: str
    coverage_targets: dict[str, int] = dataclass_field(default_factory=dict)
    identifier_policy: str | None = None


@dataclass(frozen=True, slots=True)
class TemplateEntry:
    id: str
    weight: str
    text: str


@dataclass(frozen=True, slots=True)
class Pack:
    """A fully loaded, cross-validated pack."""

    root: Path
    name: str
    version: str
    requires_core: CoreRange
    locale: str
    allowed_identifier_policies: tuple[str, ...]
    entity_lexicons: dict[str, tuple[str, ...]]
    description: str
    description_tr: str
    dataset_license: str
    record_types: tuple[RecordType, ...]
    recipes: dict[str, Recipe]
    template_sets: dict[str, tuple[TemplateEntry, ...]]
    lexicons: dict[str, tuple[str, ...]]
    digest: str

    def record_type(self, name: str) -> RecordType:
        for record_type in self.record_types:
            if record_type.type_name == name:
                return record_type
        raise KeyError(name)

    def recipe(self, name: str) -> Recipe:
        if name not in self.recipes:
            available = ", ".join(sorted(self.recipes)) or "none"
            raise KeyError(f"no recipe named {name!r}; this pack declares: {available}")
        return self.recipes[name]


def _validate(path: Path, document: dict[str, Any], definition: str | None = None) -> None:
    schema = (
        SCHEMA if definition is None else {**SCHEMA["$defs"][definition], "$defs": SCHEMA["$defs"]}
    )
    validator = jsonschema.Draft202012Validator(schema)
    first = min(
        validator.iter_errors(document),
        key=lambda error: list(error.absolute_path),
        default=None,
    )
    if first is not None:
        location = "/".join(str(part) for part in first.absolute_path) or "document"
        raise PackError(path, location, "schema", first.message)


def record_count_problem(counts: Mapping[str, object]) -> tuple[str, str] | None:
    total = 0
    for name, count in counts.items():
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            return "record-count-shape", f"record count for {name!r} is a non-negative integer"
        if count > MAX_RECORDS_PER_TYPE:
            return (
                "record-count-limit",
                f"record count for {name!r} is {count}; maximum is {MAX_RECORDS_PER_TYPE}",
            )
        total += count
    if total > MAX_TOTAL_RECORDS:
        return (
            "total-record-count-limit",
            f"total record count is {total}; maximum is {MAX_TOTAL_RECORDS}",
        )
    return None


def _validate_record_counts(path: Path, counts: Mapping[str, object]) -> None:
    problem = record_count_problem(counts)
    if problem is not None:
        rule, detail = problem
        raise PackError(path, "records", rule, detail)


def _declaration_paths(directory: Path, *, recursive: bool = False) -> list[Path]:
    if not directory.is_dir():
        return []
    iterator = directory.rglob("*.yaml") if recursive else directory.glob("*.yaml")
    paths: list[Path] = []
    for path in iterator:
        relative = path.relative_to(directory)
        if any(part.startswith(".") for part in relative.parts):
            continue
        paths.append(path)
        if len(paths) > MAX_DECLARATION_FILES:
            raise PackError(
                directory,
                "declarations",
                "declaration-file-limit",
                f"a declaration directory may contain at most {MAX_DECLARATION_FILES} YAML files",
            )
    return sorted(paths)


def _decimal(
    path: Path,
    location: str,
    raw: str,
    *,
    probability: bool = False,
) -> Decimal:
    """Parse one pack decimal under the sampler's finite-domain contract."""
    try:
        value = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise PackError(path, location, "invalid-decimal", f"{raw!r} is not a decimal") from exc
    if not value.is_finite():
        raise PackError(path, location, "invalid-decimal", f"{raw!r} is not finite")
    exponent = value.as_tuple().exponent
    places = max(0, -exponent) if isinstance(exponent, int) else MAX_DECIMAL_PLACES + 1
    if places > MAX_DECIMAL_PLACES:
        raise PackError(
            path,
            location,
            "decimal-precision-limit",
            f"{raw!r} has {places} decimal places; at most {MAX_DECIMAL_PLACES} are supported",
        )
    if probability and not Decimal(0) <= value <= Decimal(1):
        raise PackError(path, location, "probability-out-of-range", f"{raw!r} is not in [0, 1]")
    return value


def _decimal_places(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    if not isinstance(exponent, int):
        return MAX_DECIMAL_PLACES + 1
    return max(0, -exponent)


def _validate_weights(path: Path, location: str, weights: tuple[str, ...] | list[str]) -> None:
    values = [_decimal(path, f"{location}/{index}", raw) for index, raw in enumerate(weights)]
    if any(value < 0 for value in values):
        raise PackError(path, location, "negative-weight", "weights must not be negative")
    places = max((_decimal_places(value) for value in values), default=0)
    factor = Decimal(10) ** places
    total = sum(int(value * factor) for value in values)
    if total <= 0:
        raise PackError(path, location, "zero-weight-total", "weights must sum to a positive value")
    if total > TWO64:
        raise PackError(
            path,
            location,
            "sampler-domain-limit",
            f"scaled weight total {total} exceeds the 64-bit sampler domain",
        )


def _validate_probability(path: Path, location: str, raw: str) -> None:
    _decimal(path, location, raw, probability=True)


def load_pack(root: Path, *, core_version: str | None = None) -> Pack:
    """Load and cross-validate a pack directory."""
    root = Path(root)
    if not root.is_dir():
        raise PackError(root, "pack", "not-a-directory", "a pack must be a directory")
    try:
        initial_digest = pack_digest(root)
    except (NotADirectoryError, PackDigestError) as exc:
        raise PackError(root, "pack", "unsafe-pack-tree", str(exc)) from exc

    manifest_path = root / "pack.yaml"
    if not manifest_path.exists():
        raise PackError(root, "pack.yaml", "missing-pack-manifest", "every pack declares pack.yaml")

    manifest = load_yaml(manifest_path)
    _validate(manifest_path, manifest)

    requires_core = parse_range(manifest["requires_core"])
    if core_version is None:
        core_version = VERSION
    if not requires_core.contains(core_version):
        raise PackError(
            manifest_path,
            "requires_core",
            "core-version-out-of-range",
            f"this core is {core_version}, outside {requires_core.text}",
        )

    record_types = _load_record_types(root)
    template_sets = _load_template_sets(root)
    lexicons = _load_lexicons(root)
    entity_lexicons = {
        label: tuple(names) for label, names in sorted(manifest.get("entity_lexicons", {}).items())
    }
    recipes = _load_recipes(root, record_types)

    _cross_validate(
        root, record_types, recipes, template_sets, lexicons, entity_lexicons, manifest_path
    )

    try:
        final_digest = pack_digest(root)
    except (NotADirectoryError, PackDigestError) as exc:
        raise PackError(root, "pack", "unsafe-pack-tree", str(exc)) from exc
    if final_digest != initial_digest:
        raise PackError(
            root,
            "pack",
            "pack-changed-during-load",
            "declarative files changed while the pack was being parsed",
        )

    return Pack(
        root=root,
        name=manifest["name"],
        version=manifest["version"],
        requires_core=requires_core,
        locale=manifest["locale"],
        allowed_identifier_policies=tuple(manifest["allowed_identifier_policies"]),
        entity_lexicons=entity_lexicons,
        description=manifest["description"],
        description_tr=manifest["description_tr"],
        dataset_license=manifest["dataset_license"],
        record_types=record_types,
        recipes=recipes,
        template_sets=template_sets,
        lexicons=lexicons,
        digest=final_digest,
    )


def _load_record_types(root: Path) -> tuple[RecordType, ...]:
    directory = root / "fields"
    types: list[RecordType] = []
    for path in _declaration_paths(directory):
        document = load_yaml(path)
        _validate(path, document, "recordType")
        fields = tuple(
            Field(
                name=f["name"],
                type=f["type"],
                generator=f["generator"],
                pii_label=f["pii_label"],
                params=f.get("params", {}),
                ref=(
                    RefSpec(
                        parent=f["ref"]["parent"],
                        counts=tuple(f["ref"]["counts"]),
                        weights=tuple(f["ref"]["weights"]),
                    )
                    if "ref" in f
                    else None
                ),
                nullable=f.get("nullable", False),
                null_rate=f.get("null_rate"),
            )
            for f in document["fields"]
        )
        types.append(
            RecordType(
                type_name=document["type_name"],
                id_prefix=document["id_prefix"],
                order=document["order"],
                fields=fields,
            )
        )
    if len(types) > MAX_RECORD_TYPES:
        raise PackError(
            directory,
            "record-types",
            "record-type-limit",
            f"a pack may declare at most {MAX_RECORD_TYPES} record types",
        )
    return tuple(sorted(types, key=lambda t: t.order))


def _load_recipes(root: Path, record_types: tuple[RecordType, ...]) -> dict[str, Recipe]:
    directory = root / "recipes"
    known = {t.type_name for t in record_types}
    recipes: dict[str, Recipe] = {}
    for path in _declaration_paths(directory):
        document = load_yaml(path)
        _validate(path, document, "recipe")

        for type_name in document["records"]:
            if type_name not in known:
                raise PackError(
                    path,
                    f"records/{type_name}",
                    "unknown-record-type",
                    f"no field file declares {type_name!r}; declared: "
                    + (", ".join(sorted(known)) or "none"),
                )

        window = DateWindow(
            start=_parse_instant(path, "date_window/start", document["date_window"]["start"]),
            end=_parse_instant(path, "date_window/end", document["date_window"]["end"]),
        )
        if window.end <= window.start:
            raise PackError(
                path, "date_window", "inverted-window", "the window ends at or before it starts"
            )

        recipe = Recipe(
            name=document["name"],
            records=dict(document["records"]),
            date_window=window,
            special_rate=document["special_rate"],
            coverage_targets=dict(document.get("coverage_targets", {})),
            identifier_policy=document.get("identifier_policy"),
        )
        _validate_record_counts(path, recipe.records)
        _validate_probability(path, "special_rate", recipe.special_rate)
        if recipe.name in recipes:
            raise PackError(path, "name", "duplicate-recipe", f"{recipe.name!r} declared twice")
        recipes[recipe.name] = recipe
        if len(recipes) > MAX_RECIPES:
            raise PackError(
                directory,
                "recipes",
                "recipe-limit",
                f"a pack may declare at most {MAX_RECIPES} recipes",
            )
    return recipes


def _parse_instant(path: Path, location: str, text: str) -> datetime:
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PackError(
            path, location, "bad-instant", f"{text!r} is not an ISO 8601 instant"
        ) from exc
    if value.tzinfo is None:
        raise PackError(path, location, "naive-instant", f"{text!r} carries no time zone offset")
    return value


def _load_template_sets(root: Path) -> dict[str, tuple[TemplateEntry, ...]]:
    directory = root / "templates"
    pending: dict[str, list[TemplateEntry]] = {}
    for path in _declaration_paths(directory, recursive=True):
        document = load_yaml(path)
        entries = document.get("entries")
        if not isinstance(entries, list):
            raise PackError(path, "entries", "missing-entries", "a template set declares entries")
        _validate(path, entries, "templateSet")  # type: ignore[arg-type]
        name = path.parent.name if path.parent != directory else path.stem
        pending.setdefault(name, [])
        loaded_entries = tuple(
            TemplateEntry(id=e["id"], weight=e["weight"], text=e["text"]) for e in entries
        )
        _validate_weights(path, "entries/weight", [entry.weight for entry in loaded_entries])
        pending[name].extend(loaded_entries)
        if len(pending[name]) > MAX_TEMPLATE_ENTRIES_PER_SET:
            raise PackError(
                path,
                "entries",
                "template-entry-limit",
                f"template set {name!r} may contain at most {MAX_TEMPLATE_ENTRIES_PER_SET} entries",
            )
    return {name: tuple(entries) for name, entries in pending.items()}


def _load_lexicons(root: Path) -> dict[str, tuple[str, ...]]:
    directory = root / "lexicons"
    lexicons: dict[str, tuple[str, ...]] = {}
    for path in _declaration_paths(directory):
        document = load_yaml(path)
        name = document.get("name", path.stem)
        if not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9_]*", name) is None:
            raise PackError(path, "name", "lexicon-name", f"invalid lexicon name {name!r}")
        if name in lexicons:
            raise PackError(path, "name", "duplicate-lexicon", f"{name!r} declared twice")
        unknown = set(document) - {"name", "source_note", "values"}
        if unknown:
            raise PackError(
                path,
                "document",
                "lexicon-unknown-field",
                f"unsupported lexicon fields: {sorted(unknown)}",
            )
        values = document.get("values")
        if not isinstance(values, list) or not values:
            raise PackError(path, "values", "lexicon-shape", "values is a non-empty list")
        if len(values) > MAX_LEXICON_ITEMS:
            raise PackError(
                path,
                "values",
                "lexicon-item-limit",
                f"a lexicon may contain at most {MAX_LEXICON_ITEMS} values",
            )
        if not all(isinstance(value, str) for value in values):
            raise PackError(path, "values", "lexicon-value-type", "every lexicon value is a string")
        if any(len(value) > MAX_LEXICON_VALUE_CHARS for value in values):
            raise PackError(
                path,
                "values",
                "lexicon-value-limit",
                f"lexicon values may contain at most {MAX_LEXICON_VALUE_CHARS} characters",
            )
        lexicons[name] = tuple(values)
    return lexicons


def _cross_validate(
    root: Path,
    record_types: tuple[RecordType, ...],
    recipes: dict[str, Recipe],
    template_sets: dict[str, tuple[TemplateEntry, ...]],
    lexicons: dict[str, tuple[str, ...]],
    entity_lexicons: dict[str, tuple[str, ...]],
    manifest_path: Path,
) -> None:
    """The checks no single file can make about itself."""
    path = root / "fields"

    type_names = Counter(t.type_name for t in record_types)
    duplicate_type_names = sorted(name for name, count in type_names.items() if count > 1)
    if duplicate_type_names:
        raise PackError(
            path,
            "type_name",
            "duplicate-record-type",
            f"record type names declared more than once: {duplicate_type_names}",
        )

    orders = Counter(t.order for t in record_types)
    duplicates = sorted(order for order, count in orders.items() if count > 1)
    if duplicates:
        raise PackError(
            path, "order", "duplicate-order", f"two record types claim order {duplicates}"
        )

    prefixes = Counter(t.id_prefix for t in record_types)
    duplicate_prefixes = sorted(prefix for prefix, count in prefixes.items() if count > 1)
    if duplicate_prefixes:
        raise PackError(
            path,
            "id_prefix",
            "duplicate-id-prefix",
            f"two record types share the prefix {duplicate_prefixes}; identifiers would collide",
        )

    known_types = {t.type_name for t in record_types}
    order_of = {t.type_name: t.order for t in record_types}

    for record_type in record_types:
        names = Counter(f.name for f in record_type.fields)
        duplicate_names = sorted(name for name, count in names.items() if count > 1)
        if duplicate_names:
            raise PackError(
                path / f"{record_type.type_name}.yaml",
                "fields",
                "duplicate-field-name",
                f"{duplicate_names} declared more than once",
            )

        if len(record_type.document_fields) > 1:
            raise PackError(
                path / f"{record_type.type_name}.yaml",
                "fields",
                "multiple-document-fields",
                "a record type may declare at most one document field",
            )

        for declared in record_type.fields:
            _validate_field(
                path, record_type, declared, known_types, order_of, template_sets, lexicons
            )

    for recipe_name, recipe in recipes.items():
        for record_type in record_types:
            child_count = recipe.records.get(record_type.type_name, 0)
            for declared in record_type.fields:
                if declared.ref is None:
                    continue
                parent_count = recipe.records.get(declared.ref.parent, 0)
                minimum = min(declared.ref.counts)
                maximum = max(declared.ref.counts)
                low, high = parent_count * minimum, parent_count * maximum
                if not low <= child_count <= high:
                    raise PackError(
                        root / "recipes" / f"{recipe_name}.yaml",
                        f"records/{record_type.type_name}",
                        "infeasible-reference-cardinality",
                        f"{child_count} records cannot satisfy {minimum}..{maximum} per "
                        f"{declared.ref.parent} across {parent_count} parents; feasible "
                        f"total is {low}..{high}",
                    )

    _check_everything_declared_is_reachable(
        root, record_types, template_sets, lexicons, entity_lexicons, manifest_path
    )


LEX_SLOT = re.compile(r"\{lex:\s*([a-z][a-z0-9_]*)\s*\}")


def _check_everything_declared_is_reachable(
    root: Path,
    record_types: tuple[RecordType, ...],
    template_sets: dict[str, tuple[TemplateEntry, ...]],
    lexicons: dict[str, tuple[str, ...]],
    entity_lexicons: dict[str, tuple[str, ...]],
    manifest_path: Path,
) -> None:
    """Nothing a pack ships may be unreachable from the generators.

    A lexicon no generator names, or a template set no field draws from, is a file
    that looks like data and reaches none. The failure is silent and durable: it
    survives review, it survives the denylist scan, and the tests written to guard
    it guard nothing. Both are refused by name instead.
    """
    for label, names in sorted(entity_lexicons.items()):
        for name in names:
            if name not in lexicons:
                raise PackError(
                    manifest_path,
                    f"entity_lexicons/{label}",
                    "unknown-lexicon",
                    f"names lexicon {name!r}, which this pack does not declare; declared: "
                    + (", ".join(sorted(lexicons)) or "none"),
                )

    named_sets = {
        f.generator_argument
        for record_type in record_types
        for f in record_type.fields
        if f.generator_kind == "grammar"
    }
    for set_name in sorted(set(template_sets) - named_sets):
        raise PackError(
            root / "templates" / set_name,
            "templates",
            "unreachable-template-set",
            f"no field declares grammar:{set_name}, so nothing ever renders it",
        )

    named_lexicons = {
        f.generator_argument
        for record_type in record_types
        for f in record_type.fields
        if f.generator_kind == "lexicon"
    }
    named_lexicons |= {name for names in entity_lexicons.values() for name in names}
    for entries in template_sets.values():
        for entry in entries:
            named_lexicons |= set(LEX_SLOT.findall(entry.text))
    for name in sorted(set(lexicons) - named_lexicons):
        raise PackError(
            root / "lexicons" / f"{name}.yaml",
            "lexicons",
            "unreachable-lexicon",
            f"nothing draws from {name!r}: no field generator, no entity_lexicons "
            "entry, and no {lex:...} slot names it",
        )


def _validate_field(
    path: Path,
    record_type: RecordType,
    declared: Field,
    known_types: set[str],
    order_of: dict[str, int],
    template_sets: dict[str, tuple[TemplateEntry, ...]],
    lexicons: dict[str, tuple[str, ...]],
) -> None:
    location = f"{record_type.type_name}/{declared.name}"
    file_path = path / f"{record_type.type_name}.yaml"

    if declared.type == "doc" and declared.generator_kind != "grammar":
        raise PackError(
            file_path,
            location,
            "document-generator",
            "a document field must use a grammar generator",
        )
    if declared.generator_kind == "grammar" and declared.type != "doc":
        raise PackError(
            file_path,
            location,
            "grammar-field-type",
            "a grammar generator may only populate a document field",
        )
    if declared.type == "doc" and declared.pii_label != "none":
        raise PackError(
            file_path,
            location,
            "document-field-label",
            "a document's PII is represented by spans; its field label must be none",
        )

    if declared.generator_kind == "identifier":
        expected_label = declared.generator_argument
        if declared.pii_label != expected_label:
            raise PackError(
                file_path,
                location,
                "identifier-label-mismatch",
                f"{declared.generator!r} requires pii_label {expected_label!r}",
            )
    if declared.generator == "derived:email_from_name" and declared.pii_label != "EMAIL":
        raise PackError(
            file_path,
            location,
            "derived-email-label",
            "derived:email_from_name requires pii_label 'EMAIL'",
        )

    if declared.type == "ref":
        if declared.ref is None:
            raise PackError(file_path, location, "missing-ref", "a ref field declares ref")
        parent = declared.ref.parent
        if parent not in known_types:
            raise PackError(
                file_path,
                location,
                "unknown-parent",
                f"references {parent!r}, which no field file declares",
            )
        if order_of[parent] >= record_type.order:
            raise PackError(
                file_path,
                location,
                "forward-reference",
                f"references {parent!r}, which is generated at or after this type; "
                "a parent must exist before its children",
            )
        if len(declared.ref.counts) != len(declared.ref.weights):
            raise PackError(
                file_path,
                location,
                "ref-shape-mismatch",
                f"{len(declared.ref.counts)} counts against {len(declared.ref.weights)} weights",
            )
        _validate_weights(file_path, f"{location}/ref/weights", declared.ref.weights)
    elif declared.ref is not None:
        raise PackError(
            file_path, location, "ref-on-non-ref-field", f"type is {declared.type!r}, not ref"
        )

    if "age_years" in declared.params:
        # An age window only means something to the timestamp generator. Declared
        # anywhere else it would be read by nothing, and a parameter that is
        # silently ignored is worse than one that is rejected.
        if declared.generator_kind != "datetime_window":
            raise PackError(
                file_path,
                location,
                "age-years-on-wrong-generator",
                f"declares age_years but its generator is {declared.generator!r}; "
                "only datetime_window reads it",
            )
        span = declared.params["age_years"]
        if not isinstance(span, list) or len(span) != 2:
            raise PackError(
                file_path, location, "age-years-shape", "age_years is a list of two integers"
            )
        if not all(isinstance(bound, int) and not isinstance(bound, bool) for bound in span):
            raise PackError(file_path, location, "age-years-shape", "age_years bounds are integers")
        if not 0 <= span[0] < span[1]:
            raise PackError(
                file_path,
                location,
                "age-years-range",
                f"age_years is {span!r}; the bounds run from zero upward and low is below high",
            )

    if declared.generator_kind == "grammar":
        set_name = declared.generator_argument
        if set_name not in template_sets:
            raise PackError(
                file_path,
                location,
                "unknown-template-set",
                f"names template set {set_name!r}; declared: "
                + (", ".join(sorted(template_sets)) or "none"),
            )

    if declared.generator_kind == "lexicon":
        lexicon_name = declared.generator_argument
        if lexicon_name not in lexicons and not lexicon_name.endswith("_tr"):
            raise PackError(
                file_path,
                location,
                "unknown-lexicon",
                f"names lexicon {lexicon_name!r}, which the pack does not declare and "
                "which is not a core lexicon",
            )

    if declared.generator_kind == "int_uniform":
        low = declared.params.get("low", 0)
        high = declared.params.get("high", 1)
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in (low, high)):
            raise PackError(
                file_path, location, "integer-range-shape", "int_uniform bounds are integers"
            )
        if high < low:
            raise PackError(file_path, location, "integer-range-order", "high is below low")
        width = high - low + 1
        if width > TWO64:
            raise PackError(
                file_path,
                location,
                "sampler-domain-limit",
                f"inclusive integer range width {width} exceeds the 64-bit sampler domain",
            )

    if declared.generator_kind == "enum_weighted":
        values = declared.params.get("values", [])
        weights = declared.params.get("weights", [])
        if (
            not isinstance(values, list)
            or not isinstance(weights, list)
            or len(values) != len(weights)
        ):
            raise PackError(
                file_path,
                location,
                "weighted-enum-shape",
                "enum_weighted declares equally sized values and weights lists",
            )
        _validate_weights(file_path, f"{location}/params/weights", weights)

    if declared.null_rate is not None and not declared.nullable:
        raise PackError(
            file_path,
            location,
            "null-rate-without-nullable",
            "declares null_rate but is not nullable",
        )
    if declared.null_rate is not None:
        _validate_probability(file_path, f"{location}/null_rate", declared.null_rate)
