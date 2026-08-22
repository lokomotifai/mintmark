"""Strict, fail-closed YAML loading.

A pack is untrusted input. It arrives from a separate repository, is edited by
people who do not read this code, and decides what a mint emits. So every
ambiguity in it is refused rather than resolved.

`yaml.safe_load` prevents arbitrary object construction and nothing else. It
accepts duplicate keys and silently keeps the last one. It expands anchors and
aliases, so one declaration can silently become many. It honors merge keys, so a
field set can inherit properties that never appear where a reviewer reads them.
It parses multi-document streams and hands back only the first. Each of those is
a way for a pack to mean something other than what it looks like, which is
exactly what a reviewer cannot catch.

This module refuses all of them. Every rejection names the file, the location,
and the rule, because a fail-closed error that does not say what would have
worked just moves the guessing somewhere else.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode, Node

MERGE_TAG = "tag:yaml.org,2002:merge"
MAX_YAML_BYTES = 1 << 20
MAX_YAML_DEPTH = 64
MAX_YAML_NODES = 100_000
MAX_YAML_SCALAR_CHARS = 256_000


class PackError(Exception):
    """A pack is malformed. Always exits 2: unknown input fails closed."""

    def __init__(self, path: Path | str, location: str, rule: str, detail: str) -> None:
        self.path = str(path)
        self.location = location
        self.rule = rule
        self.detail = detail
        super().__init__(f"{self.path}: {location}: {rule}: {detail}")


@dataclass(frozen=True, slots=True)
class Rejection:
    """One rejection rule, named so that tests can enumerate them."""

    rule: str
    detail: str


class StrictLoader(yaml.SafeLoader):
    """A SafeLoader with every ambiguity removed.

    Subclassing rather than post-processing is deliberate: duplicate keys and
    merge keys are gone by the time a parsed document exists, so a check written
    against the result could never see them.
    """

    def __init__(self, stream: Any) -> None:
        super().__init__(stream)
        self._compose_depth = 0
        self._composed_nodes = 0

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            # The merge key is checked before the key is constructed. Constructing
            # it raises a generic "no constructor for tag" error, which rejects the
            # pack for the right outcome under the wrong name, and a rule that
            # cannot say its own name is a rule nobody can act on.
            if getattr(key_node, "tag", None) == MERGE_TAG:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "merge keys are not allowed; a pack must say what it means in place",
                    key_node.start_mark,
                )
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"duplicate key {key!r}; a later value would silently win",
                    key_node.start_mark,
                )
            seen.add(key)
        mapping: dict[Any, Any] = super().construct_mapping(node, deep=deep)
        return mapping

    def flatten_mapping(self, node: MappingNode) -> None:
        """Never expand a merge key.

        construct_mapping rejects merge keys by name before reaching here. This
        override exists so that no expansion happens through any other path.
        """
        return

    def compose_node(self, parent: Node | None, index: Any) -> Any:
        """Refuse anchors and aliases.

        Both are read from the parser event rather than from the composed node.
        PyYAML records an anchor in its anchor table and on the event, but never
        on the Node object, so a check against `node.anchor` reads None for every
        node and silently permits everything. The test that caught that is
        test_loader_rule_fires_for_its_own_reason.
        """
        if self.check_event(yaml.events.AliasEvent):
            event = self.peek_event()  # type: ignore[no-untyped-call]
            raise ConstructorError(
                None,
                None,
                "aliases are not allowed; one declaration must not silently become many",
                getattr(event, "start_mark", None),
            )

        event = self.peek_event()  # type: ignore[no-untyped-call]
        if self._compose_depth >= MAX_YAML_DEPTH:
            raise ConstructorError(
                None,
                None,
                f"YAML nesting exceeds the supported depth of {MAX_YAML_DEPTH}",
                getattr(event, "start_mark", None),
            )
        self._composed_nodes += 1
        if self._composed_nodes > MAX_YAML_NODES:
            raise ConstructorError(
                None,
                None,
                f"YAML node count exceeds the supported limit of {MAX_YAML_NODES}",
                getattr(event, "start_mark", None),
            )
        scalar = getattr(event, "value", None)
        if isinstance(scalar, str) and len(scalar) > MAX_YAML_SCALAR_CHARS:
            raise ConstructorError(
                None,
                None,
                f"YAML scalar exceeds the supported length of {MAX_YAML_SCALAR_CHARS}",
                getattr(event, "start_mark", None),
            )
        anchor = getattr(event, "anchor", None)
        if anchor is not None:
            raise ConstructorError(
                None,
                None,
                f"anchor {anchor!r} is not allowed; an anchored declaration can be "
                "reused elsewhere without a reader seeing it",
                getattr(event, "start_mark", None),
            )
        self._compose_depth += 1
        try:
            return super().compose_node(parent, index)
        finally:
            self._compose_depth -= 1


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one YAML file under every rejection rule.

    Returns the document as a mapping. Anything else, including an empty file or
    a list at the root, is refused.
    """
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise PackError(
                path,
                "file",
                "non-regular-file",
                "pack declarations must be regular files, not links or special files",
            )
        with path.open("rb") as handle:
            encoded = handle.read(MAX_YAML_BYTES + 1)
    except PackError:
        raise
    except OSError as exc:
        raise PackError(path, "file", "unreadable", str(exc)) from exc
    if len(encoded) > MAX_YAML_BYTES:
        raise PackError(
            path,
            "file",
            "yaml-byte-limit",
            f"YAML files may not exceed {MAX_YAML_BYTES} bytes",
        )
    try:
        raw = encoded.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackError(path, "file", "invalid-utf8", str(exc)) from exc

    _reject_tab_indentation(path, raw)

    try:
        documents = list(islice(yaml.compose_all(raw, Loader=StrictLoader), 2))
    except ConstructorError as exc:
        raise PackError(path, _mark(exc), "strict-yaml", str(exc.problem or exc)) from exc
    except yaml.YAMLError as exc:
        raise PackError(path, _mark(exc), "malformed-yaml", str(exc)) from exc

    if len(documents) == 0:
        raise PackError(path, "document", "empty-file", "a pack file must declare something")
    if len(documents) > 1:
        raise PackError(
            path,
            "document 2",
            "multiple-documents",
            "multiple documents in one file; only the first would ever be read",
        )

    try:
        loader = StrictLoader(raw)
        document = loader.get_single_data()
    except ConstructorError as exc:
        raise PackError(path, _mark(exc), "strict-yaml", str(exc.problem or exc)) from exc
    except yaml.YAMLError as exc:
        raise PackError(path, _mark(exc), "malformed-yaml", str(exc)) from exc
    finally:
        loader.dispose()

    if not isinstance(document, dict):
        kind = type(document).__name__
        raise PackError(
            path, "document", "non-mapping-root", f"root is a {kind}, expected a mapping"
        )
    return document


def _reject_tab_indentation(path: Path, raw: str) -> None:
    """Tabs in indentation are refused before parsing.

    YAML forbids tabs for indentation, but the resulting error points at a
    consequence rather than at the tab. Naming it directly saves the reader a
    detour, and an invisible character is exactly the fault worth naming.
    """
    for number, line in enumerate(raw.splitlines(), start=1):
        stripped = line.lstrip(" ")
        if stripped.startswith("\t"):
            raise PackError(
                path,
                f"line {number}",
                "tab-indentation",
                "tabs may not be used for indentation; use spaces",
            )


def _mark(exc: yaml.YAMLError) -> str:
    mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
    if mark is None:
        return "document"
    return f"line {mark.line + 1}, column {mark.column + 1}"
