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
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import datetime
from pathlib import Path
from typing import Any

import jsonschema

from mintmark.packs.digest import pack_digest
from mintmark.packs.loader import PackError, load_yaml
from mintmark.packs.semver import CoreRange, parse_range

SCHEMA_FILENAME = "pack.schema.json"


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
    doc_mix: dict[str, str] = dataclass_field(default_factory=dict)
    coverage_targets: dict[str, int] = dataclass_field(default_factory=dict)
    identifier_policy: str | None = None
    emit_child_outside_window: bool = True


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
    description: str
    description_tr: str
    record_types: tuple[RecordType, ...]
    recipes: dict[str, Recipe]
    template_sets: dict[str, tuple[TemplateEntry, ...]]
    lexicons: dict[str, Any]
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
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.absolute_path) or "document"
        raise PackError(path, location, "schema", first.message)


def load_pack(root: Path, *, core_version: str | None = None) -> Pack:
    """Load and cross-validate a pack directory."""
    root = Path(root)
    if not root.is_dir():
        raise PackError(root, "pack", "not-a-directory", "a pack must be a directory")

    manifest_path = root / "pack.yaml"
    if not manifest_path.exists():
        raise PackError(root, "pack.yaml", "missing-pack-manifest", "every pack declares pack.yaml")

    manifest = load_yaml(manifest_path)
    _validate(manifest_path, manifest)

    requires_core = parse_range(manifest["requires_core"])
    if core_version is not None and not requires_core.contains(core_version):
        raise PackError(
            manifest_path,
            "requires_core",
            "core-version-out-of-range",
            f"this core is {core_version}, outside {requires_core.text}",
        )

    record_types = _load_record_types(root)
    template_sets = _load_template_sets(root)
    lexicons = _load_lexicons(root)
    recipes = _load_recipes(root, record_types)

    _cross_validate(root, record_types, recipes, template_sets, lexicons)

    return Pack(
        root=root,
        name=manifest["name"],
        version=manifest["version"],
        requires_core=requires_core,
        locale=manifest["locale"],
        allowed_identifier_policies=tuple(manifest["allowed_identifier_policies"]),
        description=manifest["description"],
        description_tr=manifest["description_tr"],
        record_types=record_types,
        recipes=recipes,
        template_sets=template_sets,
        lexicons=lexicons,
        digest=pack_digest(root),
    )


def _load_record_types(root: Path) -> tuple[RecordType, ...]:
    directory = root / "fields"
    if not directory.is_dir():
        return ()
    types: list[RecordType] = []
    for path in sorted(directory.glob("*.yaml")):
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
    return tuple(sorted(types, key=lambda t: t.order))


def _load_recipes(root: Path, record_types: tuple[RecordType, ...]) -> dict[str, Recipe]:
    directory = root / "recipes"
    if not directory.is_dir():
        return {}
    known = {t.type_name for t in record_types}
    recipes: dict[str, Recipe] = {}
    for path in sorted(directory.glob("*.yaml")):
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
            doc_mix=dict(document.get("doc_mix", {})),
            coverage_targets=dict(document.get("coverage_targets", {})),
            identifier_policy=document.get("identifier_policy"),
            emit_child_outside_window=document.get("emit_child_outside_window", True),
        )
        if recipe.name in recipes:
            raise PackError(path, "name", "duplicate-recipe", f"{recipe.name!r} declared twice")
        recipes[recipe.name] = recipe
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
    if not directory.is_dir():
        return {}
    sets: dict[str, tuple[TemplateEntry, ...]] = {}
    for path in sorted(directory.rglob("*.yaml")):
        document = load_yaml(path)
        entries = document.get("entries")
        if not isinstance(entries, list):
            raise PackError(path, "entries", "missing-entries", "a template set declares entries")
        _validate(path, entries, "templateSet")  # type: ignore[arg-type]
        name = path.parent.name if path.parent != directory else path.stem
        sets.setdefault(name, ())
        sets[name] = sets[name] + tuple(
            TemplateEntry(id=e["id"], weight=e["weight"], text=e["text"]) for e in entries
        )
    return sets


def _load_lexicons(root: Path) -> dict[str, Any]:
    directory = root / "lexicons"
    if not directory.is_dir():
        return {}
    lexicons: dict[str, Any] = {}
    for path in sorted(directory.glob("*.yaml")):
        document = load_yaml(path)
        name = document.get("name", path.stem)
        lexicons[name] = document
    return lexicons


def _cross_validate(
    root: Path,
    record_types: tuple[RecordType, ...],
    recipes: dict[str, Recipe],
    template_sets: dict[str, tuple[TemplateEntry, ...]],
    lexicons: dict[str, Any],
) -> None:
    """The checks no single file can make about itself."""
    path = root / "fields"

    orders = [t.order for t in record_types]
    if len(set(orders)) != len(orders):
        duplicates: list[int] = sorted({o for o in orders if orders.count(o) > 1})
        raise PackError(
            path, "order", "duplicate-order", f"two record types claim order {duplicates}"
        )

    prefixes = [t.id_prefix for t in record_types]
    if len(set(prefixes)) != len(prefixes):
        duplicate_prefixes = sorted({p for p in prefixes if prefixes.count(p) > 1})
        raise PackError(
            path,
            "id_prefix",
            "duplicate-id-prefix",
            f"two record types share the prefix {duplicate_prefixes}; identifiers would collide",
        )

    known_types = {t.type_name for t in record_types}
    order_of = {t.type_name: t.order for t in record_types}

    for record_type in record_types:
        names = [f.name for f in record_type.fields]
        if len(set(names)) != len(names):
            duplicate_names = sorted({n for n in names if names.count(n) > 1})
            raise PackError(
                path / f"{record_type.type_name}.yaml",
                "fields",
                "duplicate-field-name",
                f"{duplicate_names} declared more than once",
            )

        for declared in record_type.fields:
            _validate_field(
                path, record_type, declared, known_types, order_of, template_sets, lexicons
            )

    for name, recipe in recipes.items():
        for set_name in recipe.doc_mix:
            if set_name not in template_sets:
                raise PackError(
                    root / "recipes" / f"{name}.yaml",
                    f"doc_mix/{set_name}",
                    "unknown-template-set",
                    f"no template set named {set_name!r}; declared: "
                    + (", ".join(sorted(template_sets)) or "none"),
                )


def _validate_field(
    path: Path,
    record_type: RecordType,
    declared: Field,
    known_types: set[str],
    order_of: dict[str, int],
    template_sets: dict[str, tuple[TemplateEntry, ...]],
    lexicons: dict[str, Any],
) -> None:
    location = f"{record_type.type_name}/{declared.name}"
    file_path = path / f"{record_type.type_name}.yaml"

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

    if declared.null_rate is not None and not declared.nullable:
        raise PackError(
            file_path,
            location,
            "null-rate-without-nullable",
            "declares null_rate but is not nullable",
        )
