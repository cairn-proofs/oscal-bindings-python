"""Write the release-notes list of the public names that ``models.py`` changes.

The script compares two versions of ``src/oscal_bindings/v1/models.py``: the
old one at a git ref (default: the merge base of ``HEAD`` and ``main``) and the
new one in the working tree. It reads both with ``ast`` and does not import the
old module, because the old module has the same import path as the installed
package.

A public name is a module-level class, ``TypeAlias``, or scalar ``Annotated``
alias whose name does not start with ``_``. Each name gets a structural
signature:

1. A model class (a subclass of ``OscalBaseModel``, ``BaseModel``, or another
   model class of the module): the set of its field names and of the
   ``alias=`` strings of its ``Field(...)`` calls, inherited fields included.
2. A root model (a subclass of ``RootModel[...]``): the same set, under a
   separate kind.
3. An enum: the set of its member values.
4. An alias: the source text of its value.

A name in both modules changes type when its kind, its signature, or its class
docstring differs. The docstring is part of the comparison because the field
names alone do not tell some types apart: the old ``Status`` (of a system
component) and the new ``Status`` (of a system) have the same fields.

Matching works on two sets. The old types that need a new name are the removed
names and the old types of the names that change type. The new types that can
take an old type are the added names and the new types of the names that change
type. An old type and a new type match when their key is equal and no other
type in either set has the same key. The first pass uses kind, signature, and
docstring as the key; the second pass, on the types that are left, uses kind
and signature. All other old types are listed as "removed, no unique
counterpart".

The element-type strings come from ``get_supported_element_types()`` for the
new module, and from the same class selection and kebab-case rule, applied to
the old AST, for the old module.
"""

from __future__ import annotations

import argparse
import ast
import subprocess  # nosec B404 — fixed git argv, no shell
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pydantic
from spec_artifact import REPO_ROOT

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

MODELS_PATH = "src/oscal_bindings/v1/models.py"
OUTPUT = Path("build") / "name-changes.md"
BASE_BRANCH = "main"

# The kinds of a public name.
ENUM = "enum"
MODEL = "model"
ROOT_MODEL = "root-model"
ALIAS = "alias"
OTHER = "other"

# Bases that make a class a model. models.py imports both; neither is an OSCAL
# element, so get_supported_element_types() leaves them out.
_MODEL_BASES = frozenset({"BaseModel", "OscalBaseModel"})


_Key = tuple[object, ...]


class NameChangesError(Exception):
    """The old source cannot be read."""


@dataclass(frozen=True)
class Definition:
    """One public module-level name of a models module."""

    name: str
    kind: str
    signature: frozenset[str] | str
    doc: str
    """The cleaned docstring, or an empty string."""
    summary: str
    """The first line of the docstring, or an empty string."""
    fields: tuple[str, ...]
    """Model field names, enum member values, or the alias source, sorted."""

    @property
    def key(self) -> _Key:
        """Return the structural key: the kind and the signature."""
        return (self.kind, self.signature)

    @property
    def strict_key(self) -> _Key:
        """Return the structural key with the docstring."""
        return (self.kind, self.signature, self.doc)


@dataclass(frozen=True)
class Unmatched:
    """An old type without a unique new counterpart."""

    name: str
    kind: str
    candidates: tuple[str, ...]
    """The new names with the same structure: empty, or two or more."""
    rivals: tuple[str, ...]
    """The other old names with the same structure."""


@dataclass(frozen=True)
class NameChanges:
    """The comparison of an old and a new models module."""

    old: Mapping[str, Definition]
    new: Mapping[str, Definition]
    kept: frozenset[str]
    """Names in both modules with the same structure."""
    reused: frozenset[str]
    """Names in both modules with a different structure."""
    removed: frozenset[str]
    added: frozenset[str]
    matches: Mapping[str, str]
    """Old name -> new name of the same type, for removed and reused names."""
    unmatched: Mapping[str, Unmatched]
    """Removed and reused names without a unique new counterpart."""

    @property
    def renames(self) -> dict[str, str]:
        """Return the removed names that have a new name for their type."""
        return {o: n for o, n in self.matches.items() if o in self.removed}

    @property
    def added_without_predecessor(self) -> list[str]:
        """Return the added names that are not the new name of an old type."""
        targets = set(self.matches.values())
        return sorted(name for name in self.added if name not in targets)


# ---------------------------------------------------------------------------
# Reading a module
# ---------------------------------------------------------------------------


def _summary(node: ast.ClassDef) -> str:
    doc = ast.get_docstring(node)
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def _base_kind(base: ast.expr, kinds: Mapping[str, str]) -> str:
    if isinstance(base, ast.Subscript):
        base = base.value
    name = base.id if isinstance(base, ast.Name) else ""
    if isinstance(base, ast.Attribute):
        name = base.attr
    if name == "Enum":
        return ENUM
    if name == "RootModel":
        return ROOT_MODEL
    if name in _MODEL_BASES:
        return MODEL
    return kinds.get(name, OTHER)


def _class_kind(node: ast.ClassDef, kinds: Mapping[str, str]) -> str:
    found = [_base_kind(base, kinds) for base in node.bases]
    for kind in (ENUM, ROOT_MODEL, MODEL):
        if kind in found:
            return kind
    return OTHER


def _field_aliases(node: ast.AST) -> set[str]:
    aliases: set[str] = set()
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        func = call.func
        name = func.id if isinstance(func, ast.Name) else ""
        if name != "Field":
            continue
        for keyword in call.keywords:
            value = keyword.value
            if (
                keyword.arg == "alias"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                aliases.add(value.value)
    return aliases


def _own_fields(node: ast.ClassDef) -> tuple[set[str], set[str]]:
    names: set[str] = set()
    aliases: set[str] = set()
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
            aliases |= _field_aliases(stmt)
    return names, aliases


def _fields(
    name: str,
    classes: Mapping[str, ast.ClassDef],
    memo: dict[str, tuple[frozenset[str], frozenset[str]]],
    active: frozenset[str] = frozenset(),
) -> tuple[frozenset[str], frozenset[str]]:
    """Return the field names and aliases of a class, inherited ones included."""
    if name in memo:
        return memo[name]
    node = classes[name]
    names, aliases = _own_fields(node)
    for base in node.bases:
        if isinstance(base, ast.Name) and base.id in classes and base.id not in active:
            base_names, base_aliases = _fields(base.id, classes, memo, active | {name})
            names |= base_names
            aliases |= base_aliases
    memo[name] = (frozenset(names), frozenset(aliases))
    return memo[name]


def _model_definition(
    node: ast.ClassDef, kind: str, fields: tuple[frozenset[str], frozenset[str]]
) -> Definition:
    names, aliases = fields
    signature = frozenset(
        {f"name:{n}" for n in names} | {f"alias:{a}" for a in aliases}
    )
    return Definition(
        name=node.name,
        kind=kind,
        signature=signature,
        doc=ast.get_docstring(node) or "",
        summary=_summary(node),
        fields=tuple(sorted(names)),
    )


def _enum_definition(node: ast.ClassDef) -> Definition:
    values: set[str] = set()
    for stmt in node.body:
        if (
            isinstance(stmt, ast.Assign)
            and all(isinstance(t, ast.Name) for t in stmt.targets)
            and isinstance(stmt.value, ast.Constant)
        ):
            values.add(repr(stmt.value.value))
    return Definition(
        name=node.name,
        kind=ENUM,
        signature=frozenset(values),
        doc=ast.get_docstring(node) or "",
        summary=_summary(node),
        fields=tuple(sorted(values)),
    )


def _alias_definition(name: str, value: ast.expr) -> Definition:
    source = ast.unparse(value)
    return Definition(
        name=name, kind=ALIAS, signature=source, doc="", summary="", fields=(source,)
    )


def read_definitions(source: str) -> dict[str, Definition]:
    """Return the public module-level names of a models module source."""
    tree = ast.parse(source)
    classes = {stmt.name: stmt for stmt in tree.body if isinstance(stmt, ast.ClassDef)}
    memo: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    kinds: dict[str, str] = {}
    definitions: dict[str, Definition] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef):
            kind = _class_kind(stmt, kinds)
            kinds[stmt.name] = kind
            if stmt.name.startswith("_"):
                continue
            if kind == ENUM:
                definitions[stmt.name] = _enum_definition(stmt)
            else:
                definitions[stmt.name] = _model_definition(
                    stmt, kind, _fields(stmt.name, classes, memo)
                )
        elif (
            isinstance(stmt, ast.AnnAssign)
            and isinstance(stmt.target, ast.Name)
            and stmt.value is not None
        ):
            if not stmt.target.id.startswith("_"):
                definitions[stmt.target.id] = _alias_definition(
                    stmt.target.id, stmt.value
                )
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    definitions[target.id] = _alias_definition(target.id, stmt.value)
    return definitions


def _imported_pydantic_models(tree: ast.Module) -> list[str]:
    """Return the names imported from pydantic that are BaseModel subclasses."""
    names: list[str] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom) and stmt.module == "pydantic":
            for alias in stmt.names:
                obj = getattr(pydantic, alias.name, None)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, pydantic.BaseModel)
                    and obj is not pydantic.BaseModel
                ):
                    names.append(alias.asname or alias.name)
    return names


def element_types_from_source(source: str) -> list[str]:
    """Return ``get_supported_element_types()`` as the module would compute it.

    The selection rule matches ``_build_element_map``: every BaseModel
    subclass in the module namespace except ``BaseModel`` and
    ``OscalBaseModel``. That covers the module's model and root-model classes
    and the imported ``RootModel``.
    """
    from oscal_bindings.v1.extensions.validate_element import (  # noqa: PLC0415
        _pascal_to_kebab,
    )

    tree = ast.parse(source)
    names = [
        name
        for name, definition in read_definitions(source).items()
        if definition.kind in (MODEL, ROOT_MODEL)
    ]
    # Private model classes are in dir() too.
    names += [
        stmt.name
        for stmt in tree.body
        if isinstance(stmt, ast.ClassDef) and stmt.name.startswith("_")
    ]
    names += _imported_pydantic_models(tree)
    return sorted({_pascal_to_kebab(name) for name in names})


def current_element_types() -> list[str]:
    """Return ``get_supported_element_types()`` of the importable package."""
    from oscal_bindings import get_supported_element_types  # noqa: PLC0415

    return list(get_supported_element_types())


# ---------------------------------------------------------------------------
# Comparing two modules
# ---------------------------------------------------------------------------


def _key(definition: Definition) -> _Key:
    return definition.key


def _strict_key(definition: Definition) -> _Key:
    return definition.strict_key


def _group(keys: Mapping[str, _Key]) -> dict[_Key, list[str]]:
    groups: dict[_Key, list[str]] = defaultdict(list)
    for name, key in keys.items():
        groups[key].append(name)
    return groups


def _unique_pairs(
    sources: Mapping[str, _Key], targets: Mapping[str, _Key]
) -> dict[str, str]:
    """Return source -> target for each key held by exactly one of each.

    A name never pairs with itself: the old and the new type of a reused name
    are different types by definition.
    """
    target_groups = _group(targets)
    pairs: dict[str, str] = {}
    for key, names in _group(sources).items():
        if len(names) != 1:
            continue
        candidates = [c for c in target_groups.get(key, []) if c != names[0]]
        if len(candidates) == 1:
            pairs[names[0]] = candidates[0]
    return pairs


def compare(
    old: Mapping[str, Definition], new: Mapping[str, Definition]
) -> NameChanges:
    """Compare the public names of two models modules."""
    both = old.keys() & new.keys()
    reused = frozenset(n for n in both if old[n].strict_key != new[n].strict_key)
    kept = frozenset(both - reused)
    removed = frozenset(old.keys() - new.keys())
    added = frozenset(new.keys() - old.keys())

    matches: dict[str, str] = {}
    sources = set(removed | reused)
    targets = set(added | reused)
    # Tier 1 pairs equal structure and docstring; tier 2 pairs the rest by
    # structure alone, so a type whose docstring changed still finds its name.
    for key_of in (_strict_key, _key):
        found = _unique_pairs(
            {name: key_of(old[name]) for name in sources},
            {name: key_of(new[name]) for name in targets},
        )
        matches.update(found)
        sources -= found.keys()
        targets -= set(found.values())

    source_groups = _group({name: old[name].key for name in sources})
    target_groups = _group({name: new[name].key for name in targets})
    unmatched = {
        name: Unmatched(
            name=name,
            kind=old[name].kind,
            candidates=tuple(
                sorted(c for c in target_groups.get(old[name].key, []) if c != name)
            ),
            rivals=tuple(sorted(n for n in source_groups[old[name].key] if n != name)),
        )
        for name in sources
    }
    return NameChanges(
        old=old,
        new=new,
        kept=kept,
        reused=reused,
        removed=removed,
        added=added,
        matches=matches,
        unmatched=unmatched,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _code_list(items: Iterable[str]) -> str:
    rendered = ", ".join(f"`{item}`" for item in items)
    return rendered or "none"


def _meaning(definition: Definition) -> str:
    summary = f' "{definition.summary}"' if definition.summary else ""
    if definition.kind == ENUM:
        detail = f"values: {_code_list(definition.fields)}"
    elif definition.kind == ALIAS:
        detail = f"value: `{definition.fields[0]}`"
    else:
        detail = f"fields: {_code_list(definition.fields)}"
    return f"{definition.kind}{summary}; {detail}"


def _unmatched_reason(item: Unmatched) -> str:
    if not item.candidates:
        reason = "no new name with the same structure"
    else:
        reason = f"ambiguous: candidates {_code_list(item.candidates)}"
    if item.rivals:
        reason += f"; same structure as old {_code_list(item.rivals)}"
    return reason


def _counterpart(changes: NameChanges, name: str) -> str:
    if name in changes.matches:
        return f"`{changes.matches[name]}`"
    return f"no unique counterpart ({_unmatched_reason(changes.unmatched[name])})"


def render(
    changes: NameChanges,
    *,
    base: str,
    old_elements: Sequence[str],
    new_elements: Sequence[str],
) -> str:
    """Return the Markdown document of the name changes."""
    renames = changes.renames
    removed_only = sorted(n for n in changes.removed if n not in renames)
    added_only = changes.added_without_predecessor
    elements_removed = sorted(set(old_elements) - set(new_elements))
    elements_added = sorted(set(new_elements) - set(old_elements))

    lines = [
        "# Name changes in `oscal_bindings.v1.models`",
        "",
        f"Old: `{MODELS_PATH}` at `{base}`. New: the working tree.",
        "",
        f"1. Renamed: {len(renames)}.",
        f"2. Same name, different type: {len(changes.reused)}.",
        f"3. Removed, no unique counterpart: {len(removed_only)}.",
        f"4. Added, no old counterpart: {len(added_only)}.",
        f"5. Unchanged: {len(changes.kept)}.",
        (
            f"6. Element types removed: {len(elements_removed)}; "
            f"added: {len(elements_added)}."
        ),
        "",
        "## Renamed",
        "",
    ]
    if renames:
        lines += ["| Old name | New name | Kind |", "| --- | --- | --- |"]
        lines += [
            f"| `{old}` | `{new}` | {changes.old[old].kind} |"
            for old, new in sorted(renames.items())
        ]
    else:
        lines.append("None.")

    lines += ["", "## Same name, different type", ""]
    for index, name in enumerate(sorted(changes.reused), start=1):
        lines += [
            f"{index}. `{name}`",
            f"   1. Old: {_meaning(changes.old[name])}.",
            f"   2. New: {_meaning(changes.new[name])}.",
            f"   3. New name of the old type: {_counterpart(changes, name)}.",
        ]
    if not changes.reused:
        lines.append("None.")

    lines += ["", "## Removed", ""]
    lines += [
        f"{index}. `{name}` ({changes.old[name].kind}): "
        f"{_unmatched_reason(changes.unmatched[name])}."
        for index, name in enumerate(removed_only, start=1)
    ] or ["None."]

    lines += ["", "## Added", ""]
    lines += [
        f"{index}. `{name}` ({changes.new[name].kind})."
        for index, name in enumerate(added_only, start=1)
    ] or ["None."]

    lines += ["", "## Element types", ""]
    lines += [
        (
            f"Old: {len(old_elements)}. New: {len(new_elements)}. "
            "Strings of `get_supported_element_types()`."
        ),
        "",
        "### Removed element types",
        "",
    ]
    lines += [
        f"{index}. `{name}`" for index, name in enumerate(elements_removed, start=1)
    ] or ["None."]
    lines += ["", "### Added element types", ""]
    lines += [
        f"{index}. `{name}`" for index, name in enumerate(elements_added, start=1)
    ] or ["None."]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------


def _git(*args: str) -> str:
    try:
        result = subprocess.run(  # noqa: S603  # nosec B603 B607 — fixed argv
            ["git", *args],  # noqa: S607
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        msg = f"cannot run git: {exc}"
        raise NameChangesError(msg) from exc
    if result.returncode != 0:
        msg = f"git {' '.join(args)} failed: {result.stderr.strip()}"
        raise NameChangesError(msg)
    return result.stdout


def default_base() -> str:
    """Return the merge base of ``HEAD`` and ``main``."""
    return _git("merge-base", "HEAD", BASE_BRANCH).strip()


def old_source(ref: str) -> str:
    """Return ``models.py`` at the git ref ``ref``."""
    if not ref or ref.startswith("-"):
        msg = f"invalid git ref: {ref!r}"
        raise NameChangesError(msg)
    return _git("show", f"{ref}:{MODELS_PATH}")


def build_document(base: str | None = None) -> str:
    """Return the name-changes document for the old module at ``base``."""
    ref = base if base is not None else default_base()
    old_text = old_source(ref)
    new_text = (REPO_ROOT / MODELS_PATH).read_text(encoding="utf-8")
    changes = compare(read_definitions(old_text), read_definitions(new_text))
    return render(
        changes,
        base=ref,
        old_elements=element_types_from_source(old_text),
        new_elements=current_element_types(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Write the name-changes document. Return the exit status."""
    parser = argparse.ArgumentParser(
        description="List the public names that models.py removes, adds, and renames."
    )
    parser.add_argument(
        "--base",
        default=None,
        help="the git ref of the old models.py "
        f"(default: the merge base of HEAD and {BASE_BRANCH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="the file to write, relative to the repository root "
        "(default: build/name-changes.md)",
    )
    args = parser.parse_args(argv)
    output: Path = REPO_ROOT / args.output
    try:
        document = build_document(args.base)
    except NameChangesError as exc:
        print(exc)
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(document, encoding="utf-8")
    print(f"{output}: written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
