"""Post-process the generated ``models.py`` and check it against the manifest.

datamodel-codegen reads the hoisted schema (``scripts/hoist_names.py``), so it
emits each ``object``, ``document``, and ``enum`` type of the naming manifest
as a class with its manifest name. This script completes the module:

1. Phase 1 changes structure. It collapses each scalar ``RootModel`` to an
   ``Annotated`` alias, and it removes ``pattern=`` from the fields of a type
   that has no regex constraint (``AwareDatetime``, ``AnyUrl``, ``EmailStr``,
   numbers).
2. It adds the manifest types that codegen does not emit with their names:

   1. Each ``single-or-many`` entry becomes a ``RootModel`` of the item or a
      list of the item, and it replaces the inline union of the field.
   2. The ``document-union`` entry is the root ``RootModel``, renamed to its
      manifest name.
   3. Each ``union`` entry becomes a ``TypeAlias`` of its variants, in manifest
      order, after the last variant class. Each inline union of exactly the
      variant set becomes the alias name.

3. It names each scalar alias from its definition key without the
   ``oscal-complete-oscal-<module>:`` prefix (``LocationUuid``). A scalar has
   no manifest entry. Its name is a binding name, not a contract name.
4. It applies three guards to the result. Each guard reports every offender:

   1. Each manifest name is defined at module level in the form that its kind
      requires.
   2. Each other module-level name is a scalar alias, and its name is the
      name of a scalar definition of the vendored schema.
   3. No module-level name is defined twice, no scalar alias has a manifest
      name, and no manifest name or scalar alias is a name that a
      module-level import statement binds.

The command line reads the codegen output at ``--models`` and writes the
completed module to ``--output`` (by default the ``--models`` path) through a
temporary file and ``os.replace``. When a step or a guard fails, it writes
nothing to ``--output``.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import stat
import sys
import tempfile
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).parent.parent

#: Default path to the generated models file (the Version_Package models path).
DEFAULT_MODELS_PATH = REPO_ROOT / "src" / "oscal_bindings" / "v1" / "models.py"
#: OSCAL release whose vendored Schema_Bundle is currently active. Schema bundles live
#: under ``schemas/<release>/``; the active one is selected by this explicit path
#: alone — never by scanning, globbing, or ordering the ``schemas/`` directory.
ACTIVE_SCHEMA_RELEASE = "1.2.3"
#: Default path to the vendored schema. The scalar names come from its definition
#: keys.
DEFAULT_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / ACTIVE_SCHEMA_RELEASE / "oscal_complete_schema.json"
)

#: The prefix of a namespaced definition key of the complete schema.
SCHEMA_KEY_PREFIX: Final = "oscal-complete-oscal-"
#: The prefix of a manifest site that is a definition of the schema.
_DEFINITION_SITE: Final = "#/definitions/"
#: The pattern of a published scalar alias name, over the full string.
_PASCAL_NAME: Final = re.compile(r"[A-Z][A-Za-z0-9]*")

#: The module-level form that each manifest kind requires (guard 1).
KIND_FORMS: Final[Mapping[str, str]] = {
    "object": "class",
    "document": "class",
    "enum": "enum",
    "union": "type alias",
    "single-or-many": "root model",
    "document-union": "root model",
}
#: The form of a scalar alias: ``Name = Annotated[...]``.
SCALAR_FORM: Final = "scalar alias"
#: The longest alias line that is written on one line, as black formats it.
LINE_LENGTH: Final = 88


class PostprocessError(ValueError):
    """Raised when the generated module cannot be completed or fails a guard.

    ``failures`` holds every failure. The message lists them, one per line.
    """

    def __init__(self, failures: Iterable[str]) -> None:
        self.failures: list[str] = list(failures)
        lines = "\n".join(f"  {failure}" for failure in self.failures)
        super().__init__(
            f"The generated models fail the post-processor "
            f"({len(self.failures)} failures):\n{lines}"
        )


# ---------------------------------------------------------------------------
# Phase 1: structure
# ---------------------------------------------------------------------------


def _kebab_to_pascal(s: str) -> str:
    """Convert kebab-case to PascalCase."""
    return "".join(word.capitalize() for word in s.split("-"))


def collapse_scalar_root_models(
    content: str, preserve: frozenset[str] = frozenset()
) -> str:
    """Convert scalar RootModel classes to ``Annotated`` aliases.

    A ``RootModel`` over a union, or one whose name is in ``preserve``, stays.
    """
    lines = content.split("\n")
    result_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Match single-line: class Name(RootModel[type]):
        m = re.match(r"^class (\w+)\(RootModel\[(.+)\]\):$", line)
        if m:
            class_name = m.group(1)
            inner_type = m.group(2)

            if class_name in preserve or "|" in inner_type:
                result_lines.append(line)
                i += 1
                continue

            # Collect body to get Field metadata
            i += 1
            body_lines = []
            while i < len(lines) and (lines[i].startswith("    ") or lines[i] == ""):
                body_lines.append(lines[i])
                i += 1
                if (
                    i < len(lines)
                    and lines[i] != ""
                    and not lines[i].startswith("    ")
                ):
                    break

            body_text = "\n".join(body_lines)
            # Extract the full Annotated type from root field if present
            annotated_match = re.search(
                r"root:\s*(Annotated\[.+?\])\s*$", body_text, re.DOTALL | re.MULTILINE
            )
            if annotated_match:
                # Multi-line Annotated - reconstruct
                # Find the root: line and everything until the closing ]
                root_start = body_text.find("root:")
                if root_start >= 0:
                    rest = body_text[root_start + 5 :].strip()
                    # Balance brackets to find the full Annotated expression
                    full_type = _extract_balanced(rest)
                    if full_type:
                        result_lines.append(f"{class_name} = {full_type}")
                        result_lines.append("")
                        result_lines.append("")
                        continue

            # Fallback: simple alias
            result_lines.append(f"{class_name} = {inner_type}")
            result_lines.append("")
            result_lines.append("")
            continue

        # Match multi-line: class Name(\n    RootModel[...]\n):
        m = re.match(r"^class (\w+)\($", line)
        if m:
            class_name = m.group(1)
            if i + 1 < len(lines) and "RootModel[" in lines[i + 1]:
                # Collect full class header
                i += 1
                header_content = line + "\n"
                while i < len(lines):
                    header_content += lines[i] + "\n"
                    if lines[i].strip() == "):" or lines[i].strip().endswith("):"):
                        i += 1
                        break
                    i += 1

                # Extract inner type
                rm_match = re.search(r"RootModel\[(.+?)\]", header_content, re.DOTALL)
                if rm_match:
                    inner_type = rm_match.group(1).strip()
                    # Normalize whitespace
                    inner_type = re.sub(r"\s+", " ", inner_type)

                    if class_name in preserve or "|" in inner_type:
                        # Keep as-is - output original lines
                        result_lines.extend(header_content.rstrip("\n").split("\n"))
                        continue

                    # Collect body
                    body_lines = []
                    while i < len(lines) and (
                        lines[i].startswith("    ") or lines[i] == ""
                    ):
                        body_lines.append(lines[i])
                        i += 1
                        if (
                            i < len(lines)
                            and lines[i] != ""
                            and not lines[i].startswith("    ")
                        ):
                            break

                    body_text = "\n".join(body_lines)
                    root_start = body_text.find("root:")
                    if root_start >= 0:
                        rest = body_text[root_start + 5 :].strip()
                        full_type = _extract_balanced(rest)
                        if full_type:
                            result_lines.append(f"{class_name} = {full_type}")
                            result_lines.append("")
                            result_lines.append("")
                            continue

                    result_lines.append(f"{class_name} = {inner_type}")
                    result_lines.append("")
                    result_lines.append("")
                    continue
            # Not a RootModel - output as-is
            result_lines.append(line)
            i += 1
            continue

        result_lines.append(line)
        i += 1

    return "\n".join(result_lines)


def _extract_balanced(text: str) -> str | None:
    """Extract a balanced expression (handling nested brackets)."""
    # If it starts with Annotated[, find the matching ]
    if not text.startswith("Annotated["):
        return text.split("\n", maxsplit=1)[0].strip() if "\n" in text else text.strip()

    depth = 0
    for idx, ch in enumerate(text):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[: idx + 1]
    return None


def ensure_annotated_import(content: str) -> str:
    """Ensure Annotated is imported from typing."""
    if (
        "Annotated" in content
        and "from typing import" in content
        and "Annotated" not in content.split("from pydantic", maxsplit=1)[0]
    ):
        # Annotated not in typing import, add it
        content = content.replace(
            "from typing import ", "from typing import Annotated, ", 1
        )
    return content


def fix_email_str_patterns(content: str) -> str:
    """Remove pattern constraints from EmailStr fields (EmailStr validates email)."""
    content = re.sub(
        r"(Annotated\[\s*EmailStr,\s*Field\([^)]*?)pattern='[^']*',?\s*",
        r"\1",
        content,
    )
    return re.sub(r",\s*\)", ")", content)


def fix_non_string_patterns(content: str) -> str:
    """Remove pattern constraints from non-string types that don't support regex."""
    # AwareDatetime, AnyUrl, int, float, bool, EmailStr don't support pattern
    # Find pattern='...' in Field() where the type is not str
    # Strategy: remove all pattern= from Annotated[AwareDatetime|AnyUrl, Field(...)]
    non_str_types = ["AwareDatetime", "AnyUrl", "int", "float", "bool", "EmailStr"]

    # Find all Field() calls that have pattern= and check if the Annotated type is
    # non-string
    lines = content.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Check if this line has a pattern= in a Field
        if "pattern=" in line and "Field(" in "\n".join(lines[max(0, i - 5) : i + 1]):
            # Look backwards to find the Annotated type
            context = "\n".join(lines[max(0, i - 10) : i + 1])
            # Check if any non-string type is in the Annotated context
            is_non_string = any(t in context for t in non_str_types)
            if is_non_string:
                # Remove the pattern='...' from this line
                line = re.sub(r"\s*pattern='[^']*',?", "", line)
                # Clean up empty Field() or trailing commas
                line = re.sub(r",\s*\)", ")", line)
                line = re.sub(r"Field\(\s*\)", "Field()", line)
        result.append(line)
        i += 1
    return "\n".join(result)


# ---------------------------------------------------------------------------
# Module-level definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Definition:
    """One module-level name of the generated source."""

    name: str
    form: str
    """``class``, ``enum``, ``root model``, ``type alias``, ``scalar alias``, or
    ``assignment``."""
    lineno: int
    end_lineno: int


def _is_name(node: ast.expr | None, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def _class_form(node: ast.ClassDef) -> str:
    if any(_is_name(base, "Enum") for base in node.bases):
        return "enum"
    if any(
        isinstance(base, ast.Subscript) and _is_name(base.value, "RootModel")
        for base in node.bases
    ):
        return "root model"
    return "class"


def module_definitions(content: str) -> list[Definition]:
    """Return each class and assignment at module level, in source order."""
    definitions: list[Definition] = []
    for node in ast.parse(content).body:
        end = node.end_lineno or node.lineno
        if isinstance(node, ast.ClassDef):
            definitions.append(
                Definition(node.name, _class_form(node), node.lineno, end)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            form = (
                "type alias" if _is_name(node.annotation, "TypeAlias") else "assignment"
            )
            definitions.append(Definition(node.target.id, form, node.lineno, end))
        elif isinstance(node, ast.Assign):
            scalar = isinstance(node.value, ast.Subscript) and _is_name(
                node.value.value, "Annotated"
            )
            form = SCALAR_FORM if scalar else "assignment"
            definitions.extend(
                Definition(target.id, form, node.lineno, end)
                for target in node.targets
                if isinstance(target, ast.Name)
            )
    return definitions


def _union_names(node: ast.expr) -> list[str] | None:
    """Return the names of a ``A | B | ...`` expression, else ``None``."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _union_names(node.left)
        right = _union_names(node.right)
        if left is not None and right is not None:
            return left + right
    return None


# ---------------------------------------------------------------------------
# Token-level rewrites
# ---------------------------------------------------------------------------


def _offsets(content: str) -> list[int]:
    """Return the offset of the start of each line (1-based line index)."""
    starts = [0, 0]
    for line in content.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return starts


def _code_tokens(content: str) -> list[tokenize.TokenInfo]:
    """Return the tokens of ``content`` without layout and comment tokens."""
    skip = {tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.INDENT}
    skip |= {tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER}
    return [
        token
        for token in tokenize.generate_tokens(io.StringIO(content).readline)
        if token.type not in skip
    ]


def _apply(content: str, edits: list[tuple[int, int, str]]) -> str:
    """Replace each ``(start, end)`` slice of ``content`` with its text."""
    for start, end, text in sorted(edits, reverse=True):
        content = content[:start] + text + content[end:]
    return content


def rename_names(content: str, renames: Mapping[str, str]) -> str:
    """Rename each NAME token in ``renames``. Strings and comments stay."""
    if not renames:
        return content
    starts = _offsets(content)
    edits = [
        (
            starts[token.start[0]] + token.start[1],
            starts[token.end[0]] + token.end[1],
            renames[token.string],
        )
        for token in _code_tokens(content)
        if token.type == tokenize.NAME and token.string in renames
    ]
    return _apply(content, edits)


def _name_runs(
    tokens: list[tokenize.TokenInfo],
) -> Iterable[tuple[int, int, list[str]]]:
    """Yield ``(first, last, names)`` for each run ``A | B | ...`` of names.

    A run that is part of an attribute, a call, or a subscript is skipped.
    """
    i = 0
    while i < len(tokens):
        if tokens[i].type != tokenize.NAME:
            i += 1
            continue
        first = last = i
        names = [tokens[i].string]
        while (
            last + 2 < len(tokens)
            and tokens[last + 1].string == "|"
            and tokens[last + 2].type == tokenize.NAME
        ):
            last += 2
            names.append(tokens[last].string)
        before = tokens[first - 1].string if first > 0 else ""
        after = tokens[last + 1].string if last + 1 < len(tokens) else ""
        if len(names) > 1 and before != "." and after not in {".", "(", "["}:
            yield first, last, names
        i = last + 1


def replace_inline_unions(content: str, aliases: Mapping[str, Sequence[str]]) -> str:
    """Replace each inline union of exactly a variant set with its alias.

    ``aliases`` maps each alias name to its variant names. The match ignores
    the order of the names and a ``None`` member, which stays at the end.
    """
    by_set = {frozenset(variants): alias for alias, variants in aliases.items()}
    tokens = _code_tokens(content)
    starts = _offsets(content)
    edits: list[tuple[int, int, str]] = []
    for first, last, names in _name_runs(tokens):
        members = [name for name in names if name != "None"]
        alias = by_set.get(frozenset(members))
        if alias is None or len(members) != len(set(members)):
            continue
        text = alias + (" | None" if "None" in names else "")
        start, end = tokens[first].start, tokens[last].end
        edits.append((starts[start[0]] + start[1], starts[end[0]] + end[1], text))
    return _apply(content, edits)


def ensure_typing_import(content: str, name: str) -> str:
    """Add ``name`` to the single-line ``from typing import ...`` statement."""
    match = re.search(r"^from typing import ([\w, ]+)$", content, flags=re.MULTILINE)
    if match is None:
        future = "from __future__ import annotations\n"
        if future in content:
            return content.replace(future, f"{future}from typing import {name}\n", 1)
        return f"from typing import {name}\n{content}"
    names = {part.strip() for part in match.group(1).split(",") if part.strip()}
    if name in names:
        return content
    line = f"from typing import {', '.join(sorted(names | {name}))}"
    return content[: match.start()] + line + content[match.end() :]


# ---------------------------------------------------------------------------
# Manifest types that codegen does not emit with their names
# ---------------------------------------------------------------------------


def _entries(manifest: Mapping[str, Any], kind: str) -> list[Mapping[str, Any]]:
    return [entry for entry in manifest.get("types", []) if entry.get("kind") == kind]


def manifest_names(manifest: Mapping[str, Any]) -> frozenset[str]:
    """Return every name of the manifest."""
    return frozenset(entry["name"] for entry in manifest.get("types", []))


def add_single_or_many(
    content: str, manifest: Mapping[str, Any], failures: list[str]
) -> str:
    """Emit each ``single-or-many`` entry as a ``RootModel`` field type.

    Codegen writes the field as ``Item | C``, where ``C`` is a ``RootModel`` of
    ``list[Item]``. ``C`` becomes the entry: a ``RootModel`` of ``Item`` or the
    list, with the list constraints of ``C``. The field takes the entry name.
    """
    for entry in _entries(manifest, "single-or-many"):
        name, item = entry["name"], entry["item"]
        candidates = [
            node
            for node in ast.parse(content).body
            if isinstance(node, ast.ClassDef)
            and len(node.bases) == 1
            and ast.unparse(node.bases[0]) == f"RootModel[list[{item}]]"
            and re.search(
                rf"\b(?:{item}\s*\|\s*{node.name}|{node.name}\s*\|\s*{item})\b",
                content,
            )
        ]
        if len(candidates) != 1:
            failures.append(
                f"{name}: expected one RootModel of list[{item}] in a field union "
                f"with {item}, found {len(candidates)}"
            )
            continue
        node = candidates[0]
        root = next(
            (
                stmt
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and _is_name(stmt.target, "root")
            ),
            None,
        )
        if root is None:
            failures.append(f"{name}: the RootModel {node.name} has no root field")
            continue
        list_type = ast.unparse(root.annotation).replace('"', "'")
        block = (
            f"class {name}(RootModel[{item} | list[{item}]]):\n"
            f"    root: {item} | {list_type}"
        )
        lines = content.split("\n")
        end = node.end_lineno or node.lineno
        content = "\n".join([*lines[: node.lineno - 1], block, *lines[end:]])
        content = re.sub(
            rf"\b(?:{item}\s*\|\s*{node.name}|{node.name}\s*\|\s*{item})\b",
            name,
            content,
        )
        if re.search(rf"\b{node.name}\b", content):
            failures.append(f"{name}: {node.name} is still referenced")
    return content


def rename_document_union(
    content: str, manifest: Mapping[str, Any], failures: list[str]
) -> str:
    """Rename the root ``RootModel`` over the document types to its entry name."""
    for entry in _entries(manifest, "document-union"):
        members = frozenset(entry.get("members", []))
        roots = [
            node.name
            for node in ast.parse(content).body
            if isinstance(node, ast.ClassDef)
            and len(node.bases) == 1
            and isinstance(node.bases[0], ast.Subscript)
            and _is_name(node.bases[0].value, "RootModel")
            and frozenset(_union_names(node.bases[0].slice) or ()) == members
        ]
        if len(roots) != 1:
            failures.append(
                f"{entry['name']}: expected one RootModel over the "
                f"{len(members)} document types, found {len(roots)}"
            )
            continue
        content = rename_names(content, {roots[0]: entry["name"]})
    return content


def _alias_text(name: str, variants: Sequence[str]) -> str:
    line = f"{name}: TypeAlias = {' | '.join(variants)}"
    if len(line) <= LINE_LENGTH:
        return line
    body = "\n    | ".join(variants)
    return f"{name}: TypeAlias = (\n    {body}\n)"


def add_union_aliases(
    content: str, manifest: Mapping[str, Any], failures: list[str]
) -> str:
    """Add a ``TypeAlias`` per ``union`` entry and use it for its inline unions.

    The alias lists the variants in manifest order. It follows the last variant
    class, because the value of an alias is evaluated at import.
    """
    aliases = {
        entry["name"]: [variant["type"] for variant in entry.get("variants", [])]
        for entry in _entries(manifest, "union")
    }
    content = replace_inline_unions(content, aliases)
    classes = {
        definition.name: definition
        for definition in module_definitions(content)
        if definition.form != SCALAR_FORM
    }
    inserts: dict[int, list[str]] = {}
    for name, variants in aliases.items():
        missing = [variant for variant in variants if variant not in classes]
        if missing:
            failures.append(
                f"{name}: the variant class(es) {', '.join(missing)} are not defined"
            )
            continue
        after = max(classes[variant].end_lineno for variant in variants)
        inserts.setdefault(after, []).append(_alias_text(name, variants))
    if not aliases:
        return content
    lines = content.split("\n")
    for after in sorted(inserts, reverse=True):
        block: list[str] = []
        for text in inserts[after]:
            block += ["", "", text]
        lines[after:after] = block
    return ensure_typing_import("\n".join(lines), "TypeAlias")


def import_bindings(content: str) -> frozenset[str]:
    """Return each name that a module-level import statement binds."""
    names: set[str] = set()
    for node in ast.parse(content).body:
        if isinstance(node, ast.Import):
            names.update(
                alias.asname or alias.name.split(".", maxsplit=1)[0]
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
    return frozenset(names)


def _site_keys(manifest: Mapping[str, Any]) -> frozenset[str]:
    """Return each definition key that is a site of a manifest entry."""
    keys: set[str] = set()
    for entry in manifest.get("types", []):
        for site in entry.get("sites", []):
            if not isinstance(site, str) or not site.startswith(_DEFINITION_SITE):
                continue
            token = site.removeprefix(_DEFINITION_SITE)
            if "/" not in token:
                keys.add(token.replace("~1", "/").replace("~0", "~"))
    return frozenset(keys)


def scalar_names(
    schema: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, str]:
    """Return the codegen name and the published name of each scalar definition.

    A scalar definition is a definition key of ``schema`` that is not a site of
    a manifest entry. A key ``oscal-complete-oscal-<module>:<local>`` gives the
    codegen name ``OscalCompleteOscal<Module><Local>`` and the published name
    ``<Local>``. Each other key, such as ``TokenDatatype``, keeps its name.
    The result maps each codegen name to its published name.
    """
    sites = _site_keys(manifest)
    names: dict[str, str] = {}
    for key in schema.get("definitions", {}):
        if key in sites:
            continue
        if key.startswith(SCHEMA_KEY_PREFIX):
            codegen_name = "".join(_kebab_to_pascal(part) for part in key.split(":"))
            names[codegen_name] = _kebab_to_pascal(key.split(":")[-1])
        else:
            name = key if key.isidentifier() else _kebab_to_pascal(key)
            names[name] = name
    return names


def scalar_renames(
    content: str,
    schema: Mapping[str, Any],
    manifest: Mapping[str, Any],
    failures: list[str],
) -> dict[str, str]:
    """Return the renames of the scalar aliases that keep a namespaced name.

    ``scalar_names`` gives the published name of each scalar definition. Only
    a module-level scalar alias outside the manifest is renamed. A published
    name that is not a PascalCase identifier, or that an import statement of
    the module binds, is added to ``failures`` and is not renamed.
    """
    scalars = {
        definition.name
        for definition in module_definitions(content)
        if definition.form == SCALAR_FORM
    }
    reserved = manifest_names(manifest)
    imports = import_bindings(content)
    renames: dict[str, str] = {}
    for codegen_name, published in scalar_names(schema, manifest).items():
        if codegen_name == published:
            continue
        if codegen_name not in scalars or codegen_name in reserved:
            continue
        if not (_PASCAL_NAME.fullmatch(published) and published.isidentifier()):
            failures.append(
                f"the scalar alias {codegen_name} cannot take the name "
                f"{published!r}: it is not a PascalCase identifier"
            )
        elif published in imports:
            failures.append(
                f"the scalar alias {codegen_name} cannot take the name "
                f"{published!r}: an import statement binds it"
            )
        else:
            renames[codegen_name] = published
    return renames


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def guard_failures(
    content: str, manifest: Mapping[str, Any], schema: Mapping[str, Any]
) -> list[str]:
    """Return every failure of the three guards on ``content``.

    ``schema`` is the vendored schema. Its scalar definitions give the names
    that a scalar alias can have (``scalar_names``).
    """
    definitions = module_definitions(content)
    by_name: dict[str, list[Definition]] = {}
    for definition in definitions:
        by_name.setdefault(definition.name, []).append(definition)
    failures: list[str] = []

    # Guard 1: each manifest name is defined in the form of its kind.
    kinds = {entry["name"]: entry["kind"] for entry in manifest.get("types", [])}
    for name, kind in kinds.items():
        expected = KIND_FORMS.get(kind)
        found = by_name.get(name, [])
        if not found:
            failures.append(f"[guard 1] the manifest name {name} ({kind}) is missing")
        elif expected is not None and all(d.form != expected for d in found):
            forms = ", ".join(d.form for d in found)
            failures.append(
                f"[guard 1] {name} ({kind}) is defined as {forms}, not as {expected}"
            )

    # Guard 2: each other module-level name is a scalar alias of a scalar
    # definition of the schema.
    failures.extend(
        f"[guard 2] {d.name} (line {d.lineno}) is defined as {d.form} outside "
        "the manifest"
        for d in definitions
        if d.name not in kinds and d.form != SCALAR_FORM
    )
    scalars = frozenset(scalar_names(schema, manifest).values())
    failures.extend(
        f"[guard 2] the scalar alias {d.name} (line {d.lineno}) names no scalar "
        "definition of the schema"
        for d in definitions
        if d.form == SCALAR_FORM and d.name not in kinds and d.name not in scalars
    )

    # Guard 3: no name is defined twice, and no scalar alias has a manifest name.
    counts = Counter(definition.name for definition in definitions)
    for name, count in sorted(counts.items()):
        if count > 1:
            lines = ", ".join(str(d.lineno) for d in by_name[name])
            failures.append(
                f"[guard 3] {name} is defined {count} times (lines {lines})"
            )
    failures.extend(
        f"[guard 3] the scalar alias {d.name} (line {d.lineno}) has a manifest name"
        for d in definitions
        if d.form == SCALAR_FORM and d.name in kinds
    )
    # Guard 3: no manifest name or scalar alias is a name that an import binds.
    imports = import_bindings(content)
    failures.extend(
        f"[guard 3] the manifest name {name} is bound by an import statement"
        for name in kinds
        if name in imports
    )
    failures.extend(
        f"[guard 3] the scalar alias {d.name} (line {d.lineno}) is bound by an "
        "import statement"
        for d in definitions
        if d.form == SCALAR_FORM and d.name not in kinds and d.name in imports
    )
    return failures


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def postprocess(
    content: str, manifest: Mapping[str, Any], schema: Mapping[str, Any]
) -> str:
    """Return the completed module. Raise ``PostprocessError`` with every failure.

    ``content`` is the codegen output for the hoisted schema, ``manifest`` is
    the validated ``names.json``, and ``schema`` is the vendored schema.
    """
    failures: list[str] = []
    content = add_single_or_many(content, manifest, failures)

    # Phase 1: structure.
    root_models = frozenset(
        entry["name"]
        for entry in manifest.get("types", [])
        if KIND_FORMS.get(entry.get("kind", "")) == "root model"
    )
    content = collapse_scalar_root_models(content, root_models)
    content = ensure_annotated_import(content)
    content = fix_email_str_patterns(content)
    content = fix_non_string_patterns(content)

    renames = scalar_renames(content, schema, manifest, failures)
    content = rename_names(content, renames)
    content = rename_document_union(content, manifest, failures)
    content = add_union_aliases(content, manifest, failures)

    # Remove the RootModel import if no longer used.
    if not re.search(r"\(RootModel\[", content):
        content = re.sub(r"\s*RootModel,?\n?", "\n", content)
        content = re.sub(r",\s*\)", "\n)", content)
    # Remove excessive blank lines.
    content = re.sub(r"\n{4,}", "\n\n\n", content)

    if failures:
        raise PostprocessError(failures)
    failures = guard_failures(content, manifest, schema)
    if failures:
        raise PostprocessError(failures)
    return content


def load_manifest(schema_path: Path) -> dict[str, Any]:
    """Return the validated manifest of the pinned spec artifact.

    The manifest must record the sha256 of the schema at ``schema_path``, so
    the scalar names and the manifest come from the same schema.

    The sibling scripts are imported here, so the module loads without
    ``scripts/`` on ``sys.path``.
    """
    from manifest import load_validated_manifest  # noqa: PLC0415
    from spec_artifact import artifact_paths, ensure_spec_artifact  # noqa: PLC0415

    return load_validated_manifest(
        artifact_paths(ensure_spec_artifact()), schema_path=schema_path
    )


def write_atomically(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` through a temporary file in its directory.

    ``os.replace`` moves the complete file into place, so a reader never sees
    a partial file. An existing file keeps its permission bits.
    """
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        tmp.chmod(mode)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    ``--models`` and ``--schema`` each carry their own default, so an omitted
    argument resolves to its own default regardless of whether the other one
    was supplied. ``--output`` defaults to the ``--models`` path.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Post-process generated models.py and check it against the manifest."
        ),
    )
    parser.add_argument(
        "--models",
        type=Path,
        default=DEFAULT_MODELS_PATH,
        help="Path to the generated models file (default: %(default)s)",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help="Path to the vendored OSCAL schema file (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write the completed module to (default: the --models path)",
    )
    args = parser.parse_args(argv)
    if args.output is None:
        args.output = args.models
    return args


def main(argv: Sequence[str] | None = None) -> int:
    """Complete and check the codegen output. Return the exit status.

    The completed module is written to ``--output`` only when every step and
    every guard passes.
    """
    args = parse_args(argv)
    models_path: Path = args.models
    schema_path: Path = args.schema
    output_path: Path = args.output

    missing = [path for path in (models_path, schema_path) if not path.exists()]
    if missing:
        for path in missing:
            print(f"Error: {path} not found", file=sys.stderr)
        return 1

    try:
        manifest = load_manifest(schema_path)
        schema = json.loads(schema_path.read_bytes())
        content = postprocess(models_path.read_text(), manifest, schema)
        write_atomically(output_path, content)
    except (ValueError, OSError) as exc:
        # ValueError covers ManifestError, PostprocessError, and invalid JSON.
        print(f"Error: {exc}", file=sys.stderr)
        print(f"{output_path} was not written", file=sys.stderr)
        return 1

    print(f"Post-processed {models_path} into {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
