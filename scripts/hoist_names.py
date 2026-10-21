"""Hoist each site of the naming manifest into a named schema definition.

datamodel-codegen names a class from the key of its schema definition. An
inline type has no key, so codegen invents a name for it. This script writes a
copy of the artifact schema in which each manifest type is a definition whose
key is its canonical name. Codegen then reads the copy and emits each class with
its manifest name. ``hoist`` makes these changes in the copy:

1. For each entry, it copies the subschema at the first site to
   ``definitions/<Name>`` and replaces every site of the entry with
   ``{"$ref": "#/definitions/<Name>"}``. It processes the deepest sites first,
   so a hoisted body already holds the ``$ref`` of each hoisted child. The
   ``document-union`` entry (site ``#``) is the root schema and stays in place.
2. For an entry with more than one site, it checks that the bodies are equal
   after step 1. The comparison ignores the annotations ``title``,
   ``description``, and ``$id`` at every depth: two merged places must have the
   same fields, field types, and constraints, and their documentation can
   differ. The definition takes the annotations of the first site.
3. It rewrites each ``$ref`` to an old definition key that was a site, and it
   removes that old key. Scalar definitions, which have no entry, keep their
   keys. The ``$id`` of a hoisted definition becomes its new pointer.
4. A closed-enum site is the ``enum`` branch of an ``allOf`` with a base
   datatype. The whole ``allOf`` object becomes the ``$ref``, with the
   ``title`` and ``description`` of the property beside it. The script first
   checks that each enum value is valid for the base datatype, so the enum
   alone accepts the same values as the ``allOf``. An open-enum site is the
   ``enum`` branch of an ``anyOf``. Only that branch becomes the ``$ref``, and
   the base datatype stays in the ``anyOf``. The definition of each enum takes
   the ``title`` and ``description`` of the schema that holds the ``allOf`` or
   ``anyOf``, so the enum class keeps its docstring.
5. The root ``oneOf`` stays. Each of its branches is a ``document`` site, so the
   root becomes a ``oneOf`` of ``$ref``s.
6. The annotations stay where codegen reads them. The ``$ref`` of a site that
   is a property keeps the ``title`` and ``description`` of the property, so
   the field keeps its documentation. A site that is a branch of an ``anyOf``
   or a ``oneOf`` below the root and has no ``description`` takes the
   ``description`` of the schema that holds the branch, so each union variant
   class keeps a docstring.

Each site is resolved in the working copy when its turn comes. A descendant of
a site has more pointer tokens than the site, so it is processed first, and no
ancestor of a site is replaced before the site. Thus each pointer still
resolves in the working copy as it does in the artifact schema.

Run this file to write ``build/codegen/oscal_complete_schema.json`` from the
artifact schema and the validated manifest of the pinned spec artifact.
"""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import jsonschema_rs
from manifest import (
    ManifestError,
    escape_token,
    format_pointer,
    load_validated_manifest,
    parse_pointer,
    read_schema_bytes,
    resolve_pointer,
)
from pinned_archive import CorpusError
from spec_artifact import REPO_ROOT, artifact_paths, ensure_spec_artifact

if TYPE_CHECKING:
    from collections.abc import Sequence

# The hoisted copy that codegen reads. It is a build file and git-ignored.
OUTPUT: Final[Path] = REPO_ROOT / "build" / "codegen" / "oscal_complete_schema.json"

# The kind of the root union. Its only site is "#", the root schema itself.
_DOCUMENT_UNION: Final = "document-union"
# Annotations that the merge comparison ignores.
_ANNOTATIONS: Final = frozenset({"title", "description", "$id"})
# The annotations that an enum definition takes from the schema that holds it.
_DOCS: Final = ("title", "description")
# Keywords whose value maps names to schemas. Their keys are names, not keywords.
_SCHEMA_MAPS: Final = frozenset({"properties", "patternProperties", "definitions"})
# A definition pointer has two tokens: "definitions" and the key. An enum site
# also ends in two tokens: the combinator and the branch index.
_PAIR: Final = 2
# The combinators whose branches are union variants.
_BRANCHES: Final = frozenset({"anyOf", "oneOf"})
# The keys that a closed-enum allOf object can hold beside its allOf.
_CLOSED_HOLDER_KEYS: Final = frozenset({"title", "description", "$id", "allOf"})


class HoistError(ValueError):
    """Raised when the manifest sites cannot be hoisted.

    ``failures`` holds every failure. The message lists them, one per line.
    """

    def __init__(self, failures: list[str]) -> None:
        self.failures: list[str] = list(failures)
        lines = "\n".join(f"  {failure}" for failure in self.failures)
        super().__init__(
            f"Cannot hoist the manifest sites ({len(self.failures)} failures):\n{lines}"
        )


@dataclass(frozen=True)
class _Site:
    """One site of one entry, and the node that its ``$ref`` replaces."""

    name: str
    pointer: str
    tokens: tuple[str, ...]
    """The tokens of ``pointer``."""
    order: tuple[int, int]
    """The index of the entry in ``types`` and of the site in ``sites``."""
    enum: str | None
    """``"open"`` or ``"closed"`` for an enum site, else ``None``."""

    @property
    def target(self) -> tuple[str, ...]:
        """The tokens of the node that becomes the ``$ref``.

        For a closed enum, it is the ``allOf`` object. For each other site, it
        is the site itself.
        """
        return self.tokens[:-_PAIR] if self.enum == "closed" else self.tokens

    @property
    def holder(self) -> tuple[str, ...]:
        """For an enum site, the tokens of the schema that holds the combinator."""
        return self.tokens[:-_PAIR]


@dataclass(frozen=True)
class _Hoisted:
    """The body of a site, taken when the site was replaced."""

    pointer: str
    site_index: int
    definition: dict[str, Any]
    """The subschema that ``definitions/<Name>`` gets from this site."""
    comparable: object
    """The body for the merge comparison, without annotations."""


def _definition_ref(name: str) -> str:
    return format_pointer(("definitions", name))


def _definition_key(pointer: str) -> str | None:
    """Return the key of a ``#/definitions/<key>`` pointer, else ``None``."""
    tokens = parse_pointer(pointer) or []
    if len(tokens) == _PAIR and tokens[0] == "definitions":
        return tokens[1]
    return None


def _strip_annotations(node: object, *, is_schema: bool = True) -> object:
    """Return a copy of ``node`` without the annotations of its schemas.

    A key under ``properties`` or ``definitions`` is a name, so a property
    named ``title`` stays.
    """
    if isinstance(node, list):
        return [_strip_annotations(item) for item in node]
    if not isinstance(node, dict):
        return node
    if not is_schema:
        return {key: _strip_annotations(value) for key, value in node.items()}
    return {
        key: _strip_annotations(value, is_schema=key not in _SCHEMA_MAPS)
        for key, value in node.items()
        if key not in _ANNOTATIONS
    }


def _first_difference(left: object, right: object, path: str = "") -> str:
    """Return the relative pointer of the first place where two values differ."""
    if isinstance(left, dict) and isinstance(right, dict):
        for key in [*left, *(k for k in right if k not in left)]:
            if key not in left or key not in right:
                return f"{path}/{escape_token(key)}"
            if left[key] != right[key]:
                return _first_difference(
                    left[key], right[key], f"{path}/{escape_token(key)}"
                )
    if isinstance(left, list) and isinstance(right, list) and len(left) == len(right):
        for i, (a, b) in enumerate(zip(left, right, strict=True)):
            if a != b:
                return _first_difference(a, b, f"{path}/{i}")
    return path or "/"


def _get(root: object, tokens: Sequence[str]) -> Any:
    """Return the node at ``tokens``. The caller has checked that it resolves."""
    node: Any = root
    for token in tokens:
        node = node[int(token)] if isinstance(node, list) else node[token]
    return node


def _set(root: object, tokens: Sequence[str], value: object) -> None:
    parent = _get(root, tokens[:-1])
    if isinstance(parent, list):
        parent[int(tokens[-1])] = value
    else:
        parent[tokens[-1]] = value


def _docs(schema: object) -> dict[str, Any]:
    """Return the ``title`` and ``description`` of ``schema``."""
    if not isinstance(schema, dict):
        return {}
    return {key: schema[key] for key in _DOCS if key in schema}


def _plan(manifest: dict[str, Any], failures: list[str]) -> list[_Site]:
    """Return every site to hoist, deepest target first."""
    sites: list[_Site] = []
    for entry_index, entry in enumerate(manifest.get("types", [])):
        kind = entry.get("kind")
        if kind == _DOCUMENT_UNION:
            continue
        name = entry["name"]
        enum = None
        if kind == "enum":
            enum = "closed" if entry.get("closed") is True else "open"
        for site_index, pointer in enumerate(entry.get("sites", [])):
            tokens = parse_pointer(pointer)
            if not tokens:
                failures.append(f"{name}: the site {pointer!r} cannot be hoisted")
                continue
            if enum is not None:
                combinator = "allOf" if enum == "closed" else "anyOf"
                if len(tokens) <= _PAIR or tokens[-2] != combinator:
                    failures.append(
                        f"{name}: the {enum}-enum site {pointer!r} is not a branch "
                        f"of an {combinator}"
                    )
                    continue
            sites.append(
                _Site(name, pointer, tuple(tokens), (entry_index, site_index), enum)
            )
    # Deepest first. Ties keep manifest order, so each run is the same.
    sites.sort(key=lambda site: (-len(site.target), site.order))
    return sites


def _base_failures(
    site: _Site, holder: dict[str, Any], definitions: dict[str, Any]
) -> list[str]:
    """Check each closed-enum value against the other branches of its ``allOf``.

    The values are checked against the original definitions, so the check sees
    the base datatype as the artifact schema defines it.
    """
    branches = holder.get("allOf")
    enum_index = int(site.tokens[-1])
    if not isinstance(branches, list) or enum_index >= len(branches):
        return [f"{site.name}: the closed-enum site {site.pointer!r} does not resolve"]
    branch = branches[enum_index]
    values = branch.get("enum") if isinstance(branch, dict) else None
    if not isinstance(values, list):
        return [f"{site.name}: the closed-enum site {site.pointer!r} holds no enum"]
    base = [b for i, b in enumerate(branches) if i != enum_index]
    if not base or not set(holder) <= _CLOSED_HOLDER_KEYS:
        return [
            (
                f"{site.name}: the closed enum at {site.pointer!r} has no base "
                "datatype, or its allOf object holds other constraints"
            )
        ]
    validator = jsonschema_rs.Draft7Validator(
        {"definitions": definitions, "allOf": base}, validate_formats=False
    )
    return [
        f"{site.name}: the closed-enum value {value!r} at {site.pointer!r} is not "
        "valid for its base datatype"
        for value in values
        if not validator.is_valid(value)
    ]


def _take(
    site: _Site,
    working: dict[str, Any],
    definitions: dict[str, Any],
    failures: list[str],
) -> _Hoisted | None:
    """Replace ``site`` in ``working`` with its ``$ref``. Return its body."""
    target = resolve_pointer(working, format_pointer(site.target))
    if target is None:
        failures.append(f"{site.name}: the site {site.pointer!r} does not resolve")
        return None
    body: Any = copy.deepcopy(target)
    ref: dict[str, Any] = {"$ref": _definition_ref(site.name)}
    if site.enum == "closed":
        site_failures = _base_failures(site, body, definitions)
        if site_failures:
            failures.extend(site_failures)
            return None
        definition = {**_docs(body), **body["allOf"][int(site.tokens[-1])]}
        ref.update(_docs(body))
    elif site.enum == "open":
        definition = {**_docs(_get(working, site.holder)), **body}
    else:
        definition = body
        if _definition_key(site.pointer) is not None and "$id" in definition:
            definition["$id"] = _definition_ref(site.name)
        parent = site.tokens[-2] if len(site.tokens) >= _PAIR else None
        if parent == "properties":
            ref.update(_docs(body))
        elif (
            parent in _BRANCHES
            and len(site.tokens) > _PAIR
            and "description" not in definition
        ):
            holder_docs = _docs(_get(working, site.holder))
            if "description" in holder_docs:
                definition["description"] = holder_docs["description"]
    _set(working, site.target, ref)
    return _Hoisted(site.pointer, site.order[1], definition, _strip_annotations(body))


def _merge_failures(name: str, hoisted: list[_Hoisted]) -> list[str]:
    """Return a failure for each site whose body differs from the first site."""
    first = hoisted[0]
    return [
        f"{name}: the body at {other.pointer!r} differs from the body at "
        f"{first.pointer!r} (first difference at "
        f"{_first_difference(first.comparable, other.comparable)})"
        for other in hoisted[1:]
        if other.comparable != first.comparable
    ]


def _definitions(
    original_keys: list[str],
    working_defs: dict[str, Any],
    hoisted: dict[str, list[_Hoisted]],
    failures: list[str],
) -> tuple[dict[str, Any], dict[str, str]]:
    """Return the new ``definitions`` and the ``$ref`` renames of old site keys.

    A hoisted definition takes the slot of the old definition key that it
    replaces. A hoisted inline type follows the definition that holds its first
    site. Each other hoisted type, such as a document wrapper, comes last.
    """
    slot: dict[str, str] = {}
    following: dict[str | None, list[str]] = {}
    renames: dict[str, str] = {}
    for name, items in hoisted.items():
        key = _definition_key(items[0].pointer)
        if key is not None:
            slot[key] = name
        else:
            tokens = parse_pointer(items[0].pointer) or []
            anchor = tokens[1] if tokens[:1] == ["definitions"] else None
            following.setdefault(anchor, []).append(name)
        for item in items:
            if _definition_key(item.pointer) is not None:
                renames[item.pointer] = _definition_ref(name)
    old_keys = {_definition_key(pointer) for pointer in renames}

    result: dict[str, Any] = {}

    def emit(key: str, value: object) -> None:
        if key in result:
            failures.append(f"the definition key {key!r} occurs more than once")
        result[key] = value

    for key in original_keys:
        if key in slot:
            emit(slot[key], hoisted[slot[key]][0].definition)
        elif key not in old_keys:
            emit(key, working_defs[key])
        for name in following.get(key, []):
            emit(name, hoisted[name][0].definition)
    for name in following.get(None, []):
        emit(name, hoisted[name][0].definition)
    return result, renames


def _rewrite_refs(node: object, renames: dict[str, str]) -> None:
    """Rewrite each ``$ref`` in ``node`` whose target is a key of ``renames``."""
    if isinstance(node, list):
        for item in node:
            _rewrite_refs(item, renames)
    elif isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref in renames:
            node["$ref"] = renames[ref]
        for value in node.values():
            _rewrite_refs(value, renames)


def _unresolved_refs(node: object, root: object, path: str = "#") -> list[str]:
    """Return a failure for each ``$ref`` in ``node`` that does not resolve."""
    failures: list[str] = []
    if isinstance(node, list):
        for i, item in enumerate(node):
            failures.extend(_unresolved_refs(item, root, f"{path}/{i}"))
    elif isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and resolve_pointer(root, ref) is None:
            failures.append(f"the $ref {ref!r} at {path!r} does not resolve")
        for key, value in node.items():
            failures.extend(
                _unresolved_refs(value, root, f"{path}/{escape_token(key)}")
            )
    return failures


def hoist(schema: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``schema`` with each manifest site hoisted.

    ``schema`` is the complete OSCAL schema that ``manifest`` describes, and
    ``manifest`` is a validated ``names.json``. Neither is changed. Raise
    ``HoistError`` with every failure. The module docstring lists the steps.
    """
    original_defs = schema.get("definitions")
    if not isinstance(original_defs, dict):
        raise HoistError(["the schema has no definitions object"])
    failures: list[str] = []
    working = copy.deepcopy(schema)
    hoisted: dict[str, list[_Hoisted]] = {}
    for site in _plan(manifest, failures):
        item = _take(site, working, original_defs, failures)
        if item is not None:
            hoisted.setdefault(site.name, []).append(item)
    # Manifest order, and each entry's sites in manifest order.
    ordered = {
        entry["name"]: sorted(hoisted[entry["name"]], key=lambda h: h.site_index)
        for entry in manifest.get("types", [])
        if entry.get("name") in hoisted
    }
    for name, items in ordered.items():
        failures.extend(_merge_failures(name, items))
    if failures:
        raise HoistError(failures)

    definitions, renames = _definitions(
        list(original_defs), working["definitions"], ordered, failures
    )
    working["definitions"] = definitions
    _rewrite_refs(working, renames)
    failures.extend(_unresolved_refs(working, working))
    if failures:
        raise HoistError(failures)
    return working


def dumps(schema: dict[str, Any]) -> str:
    """Return the text of a schema: key order kept, indent 2, final newline."""
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Write the hoisted copy of the artifact schema. Return the exit status."""
    parser = argparse.ArgumentParser(
        description="Write the hoisted copy of the artifact OSCAL schema."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="the file to write, relative to the repository root "
        "(default: build/codegen/oscal_complete_schema.json)",
    )
    args = parser.parse_args(argv)
    output: Path = REPO_ROOT / args.output
    try:
        paths = artifact_paths(ensure_spec_artifact())
        # One read: the manifest check hashes the bytes that the hoist parses.
        schema_bytes = read_schema_bytes(paths.schema)
        manifest = load_validated_manifest(paths, schema_bytes=schema_bytes)
        schema = json.loads(schema_bytes)
        result = hoist(schema, manifest)
    except (ManifestError, HoistError, CorpusError) as exc:
        print(exc)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(dumps(result), encoding="utf-8")
    added = [key for key in result["definitions"] if key not in schema["definitions"]]
    print(f"{output}: {len(added)} hoisted definitions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
