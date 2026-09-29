"""Post-process generated models.py to optimize RootModel usage and rename classes."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

REPO_ROOT = Path(__file__).parent.parent

#: Default path to the generated models file (the Version_Package models path).
DEFAULT_MODELS_PATH = REPO_ROOT / "src" / "oscal_bindings" / "v1" / "models.py"
#: OSCAL release whose vendored Schema_Bundle is currently active. Schema bundles live
#: under ``schemas/<release>/``; the active one is selected by this explicit path
#: alone — never by scanning, globbing, or ordering the ``schemas/`` directory.
#: Adding another ``schemas/<release>/`` bundle changes nothing until this constant
#: (or an explicit ``--schema`` argument) changes.
ACTIVE_SCHEMA_RELEASE = "1.2.3"
#: Default path to the source schema (the Active_Schema_Bundle schema path).
DEFAULT_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / ACTIVE_SCHEMA_RELEASE / "oscal_complete_schema.json"
)

#: Name of the generated field holding the ``$schema`` directive. It is present on
#: every Wrapper_Class and is *not* the document root key, so the derivation
#: excludes it.
SCHEMA_DIRECTIVE_FIELD = "field_schema"

#: Frozen snapshot of the positional ``Model1..Model8`` map that the content-based
#: derivation replaced. The ordinals were an artifact of the order
#: ``datamodel-codegen`` walked the schema's top-level ``oneOf``, so a schema revision
#: that added or reordered document types would have silently produced wrong names.
#:
#: This no longer drives renaming. It is retained only as the expected result for the
#: parity gate: the derivation must reproduce exactly these eight published names
#: against the Active_Schema_Bundle.
POSITIONAL_DOCUMENT_RENAMES_SNAPSHOT = {
    "Model1": "CatalogDocument",
    "Model2": "MappingCollectionDocument",
    "Model3": "ProfileDocument",
    "Model4": "ComponentDefinitionDocument",
    "Model5": "SystemSecurityPlanDocument",
    "Model6": "AssessmentPlanDocument",
    "Model7": "AssessmentResultsDocument",
    "Model8": "PlanOfActionAndMilestonesDocument",
}

ROOT_RENAME = ("Model", "OscalDocument")

VARIANT_RENAMES = {
    "OscalCompleteOscalProfileMerge1": "MergeFlat",
    "OscalCompleteOscalProfileMerge2": "MergeAsIs",
    "OscalCompleteOscalProfileMerge3": "MergeCustom",
    "OscalCompleteOscalCatalogGroup1": "CatalogGroupWithGroups",
    "OscalCompleteOscalCatalogGroup2": "CatalogGroupWithControls",
}

# Classes to NEVER collapse (keep as RootModel) - unions and the root document
PRESERVE_AS_ROOTMODEL = {"Model", "Mappings"}

# Short names that collide across modules - use module-prefixed names
COLLISION_OVERRIDES = {
    "oscal-complete-oscal-component-definition:control-implementation": (
        "ComponentDefinitionControlImplementation"
    ),
    "oscal-complete-oscal-ssp:control-implementation": "SspControlImplementation",
    "oscal-complete-oscal-catalog:group": "CatalogGroup",
    "oscal-complete-oscal-profile:group": "ProfileGroup",
    "oscal-complete-oscal-component-definition:implemented-requirement": (
        "ComponentDefinitionImplementedRequirement"
    ),
    "oscal-complete-oscal-ssp:implemented-requirement": "SspImplementedRequirement",
    "oscal-complete-oscal-control-common:select-control-by-id": (
        "ControlCommonSelectControlById"
    ),
    "oscal-complete-oscal-assessment-common:select-control-by-id": (
        "AssessmentCommonSelectControlById"
    ),
    "oscal-complete-oscal-component-definition:statement": (
        "ComponentDefinitionStatement"
    ),
    "oscal-complete-oscal-ssp:statement": "SspStatement",
    # These named definitions collide with inline definitions that datamodel-codegen
    # names after their title ("Status", "Origin", "Local Definitions"). Prefix the
    # named ones so the bare short name is left for the inline definition.
    "oscal-complete-oscal-ssp:status": "SspStatus",
    "oscal-complete-oscal-assessment-common:origin": "AssessmentCommonOrigin",
    "oscal-complete-oscal-poam:local-definitions": "PoamLocalDefinitions",
}


def _kebab_to_pascal(s: str) -> str:
    """Convert kebab-case to PascalCase."""
    return "".join(word.capitalize() for word in s.split("-"))


def _snake_to_pascal(s: str) -> str:
    """Convert snake_case to PascalCase (``plan_of_action`` -> ``PlanOfAction``)."""
    return "".join(word.capitalize() for word in s.split("_"))


def iter_class_blocks(content: str) -> Iterator[tuple[str, list[str]]]:
    """Yield ``(class_name, body_lines)`` for every class defined in ``content``.

    Blocks are yielded in source order, which is what lets the ambiguity guard report
    the *first* offending Wrapper_Class. A block ends at the next line that starts a new
    top-level statement; continuation lines of a multi-line class header (indented, or
    the closing ``):``) stay inside the block.
    """
    class_name: str | None = None
    body: list[str] = []

    for line in content.split("\n"):
        header = re.match(r"^class (\w+)\(", line)
        if header:
            if class_name is not None:
                yield class_name, body
            class_name = header.group(1)
            body = []
            continue
        if class_name is None:
            continue
        if line and not line[0].isspace() and not line.startswith(")"):
            yield class_name, body
            class_name = None
            body = []
        else:
            body.append(line)

    if class_name is not None:
        yield class_name, body


def class_field_names(body_lines: list[str]) -> list[str]:
    """Return the annotated field names declared directly on a class body, in order.

    Only the class's own indentation level is considered, so nested ``Field(...)`` and
    ``Annotated[...]`` continuation lines are ignored. ``model_config`` is an assignment
    rather than an annotation and so never matches.
    """
    return [
        m.group(1)
        for m in (re.match(r"^    (\w+)\s*:", line) for line in body_lines)
        if m is not None
    ]


class AmbiguousWrapperError(Exception):
    """A candidate Wrapper_Class carries more than one body field besides ``$schema``.

    Raised — not accumulated — on purpose. The derivation's core assumption (one
    ``$schema`` field plus exactly one Root_Key field) has failed for this schema, and
    every phase after the rename map is built on that assumption, so continuing would
    produce output whose meaning is undefined. The first offender is the whole
    diagnosis: the remedy is to go read the schema, not to read a list. See
    "Why the two guards differ" in the design document for the contrast with the
    collision guard, which deliberately accumulates.
    """

    def __init__(self, class_name: str, body_fields: Sequence[str]) -> None:
        self.class_name = class_name
        self.body_fields = list(body_fields)
        super().__init__(
            f"ambiguous wrapper class {class_name}: expected exactly one body field "
            f"besides {SCHEMA_DIRECTIVE_FIELD}, found "
            f"{len(self.body_fields)} ({', '.join(self.body_fields)})"
        )


def derive_document_renames(content: str) -> dict[str, str]:
    """Derive the Document_Rename_Map from the generated source's own content.

    A Wrapper_Class is identified by the ``$schema`` directive field it carries, never
    by the ordinal suffix in its generated name. Its Root_Key is the single remaining
    body field; the published name is that key in PascalCase with a ``Document`` suffix
    (``catalog`` -> ``CatalogDocument``). Position therefore plays no part: reordering
    the schema's document types reorders the ordinals but not the derived names.

    Raises:
        AmbiguousWrapperError: on the *first* candidate carrying more than one body
            field. ``iter_class_blocks`` yields in source order, so the offender named
            is the first one in the file and the remaining candidates are left
            unscanned.
    """
    renames: dict[str, str] = {}

    for class_name, body in iter_class_blocks(content):
        field_names = class_field_names(body)
        if SCHEMA_DIRECTIVE_FIELD not in field_names:
            continue
        body_fields = [name for name in field_names if name != SCHEMA_DIRECTIVE_FIELD]
        if len(body_fields) > 1:
            raise AmbiguousWrapperError(class_name, body_fields)
        if not body_fields:
            # The ``$schema`` directive alone: this is the union root (``Model``), not a
            # document wrapper. Nothing to derive, and not an error.
            continue
        renames[class_name] = _snake_to_pascal(body_fields[0]) + "Document"

    return renames


def count_schema_document_types(schema_path: Path) -> int | None:
    """Count the document types in a schema bundle's top-level ``oneOf``.

    Returns ``None`` when the schema has no top-level ``oneOf`` list. A bundle without
    that list does not declare document types at all, so there is no count to compare
    against and the guard has nothing to judge — reporting a mismatch against an
    assumed zero would be an assertion about a schema shape this function cannot
    observe. Every real OSCAL 1.x bundle carries the list (eight entries), so the
    guard is never skipped for the inputs it exists to police.
    """
    schema = json.loads(schema_path.read_text())
    one_of = schema.get("oneOf")
    if not isinstance(one_of, list):
        return None
    return len(one_of)


def report_wrapper_count_mismatch(
    derived: int, expected: int, models_path: Path
) -> None:
    """Print the count-mismatch report to stderr, naming both counts."""
    print(
        f"Error: derived {derived} wrapper class(es) but the schema declares "
        f"{expected} document type(s); {models_path} was not written",
        file=sys.stderr,
    )
    print(
        "The derivation and the schema disagree on the set of document types. Check "
        "the schema's top-level oneOf and the generated wrapper classes, then "
        "regenerate.",
        file=sys.stderr,
    )


def _def_key_to_codegen_name(key: str) -> str:
    """Convert a schema definition key to the class name datamodel-codegen produces."""
    # e.g. "oscal-complete-oscal-catalog:catalog" -> "OscalCompleteOscalCatalogCatalog"
    # Split on colon, PascalCase each part (treating hyphens as word separators)
    parts = key.split(":")
    return "".join(_kebab_to_pascal(p) for p in parts)


def build_namespace_renames(schema_path: Path) -> dict[str, str]:
    """Build rename map from OscalComplete* names to short names using the schema."""
    schema = json.loads(schema_path.read_text())
    definitions = schema.get("definitions", {})

    # Collect all oscal-complete keys and their short names
    short_name_counts: dict[str, list[str]] = {}
    for key in definitions:
        if key.startswith("oscal-complete-oscal-"):
            short_name = key.split(":")[-1]
            short_name_counts.setdefault(short_name, []).append(key)

    renames: dict[str, str] = {}
    for key in definitions:
        if not key.startswith("oscal-complete-oscal-"):
            continue

        codegen_name = _def_key_to_codegen_name(key)
        short_name = key.split(":")[-1]

        if key in COLLISION_OVERRIDES:
            desired = COLLISION_OVERRIDES[key]
        else:
            desired = _kebab_to_pascal(short_name)

        renames[codegen_name] = desired

    return renames


def collapse_scalar_root_models(content: str) -> str:
    """Convert scalar RootModel classes to TypeAlias."""
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

            if class_name in PRESERVE_AS_ROOTMODEL or "|" in inner_type:
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

                    if class_name in PRESERVE_AS_ROOTMODEL or "|" in inner_type:
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


def rename_classes(content: str, renames: dict[str, str]) -> str:
    """Rename classes and all their references using word boundaries."""
    for old_name, new_name in renames.items():
        content = re.sub(rf"\b{re.escape(old_name)}\b", new_name, content)
    return content


def rename_root_model(content: str) -> str:
    """Rename the root Model class carefully (avoid renaming BaseModel, ConfigDict)."""
    # Only rename standalone 'Model' references (not part of BaseModel, RootModel, etc.)
    # Replace class definition
    content = re.sub(
        r"^class Model\(", "class OscalDocument(", content, flags=re.MULTILINE
    )
    # Replace references that are standalone Model (word boundary, not preceded by
    # Base/Root/Config)
    return re.sub(r"(?<![A-Za-z])Model(?![A-Za-z0-9_])", "OscalDocument", content)


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


def find_duplicate_class_definitions(content: str) -> dict[str, int]:
    """Return every class name defined more than once, mapped to its definition count.

    Run against the *fully renamed* source: a name appearing twice there means two
    distinct schema definitions collapsed onto one published name, which
    ``COLLISION_OVERRIDES`` did not disambiguate. The whole content is scanned in
    one pass so all collisions are collected rather than stopping at the first.
    """
    counts = Counter(re.findall(r"^class (\w+)\(", content, flags=re.MULTILINE))
    return {name: count for name, count in sorted(counts.items()) if count > 1}


def report_collisions(duplicates: dict[str, int], models_path: Path) -> None:
    """Print the complete accumulated collision report to stderr."""
    print(
        f"Error: {len(duplicates)} class-name collision(s) not covered by "
        f"COLLISION_OVERRIDES; {models_path} was not written",
        file=sys.stderr,
    )
    for name, count in duplicates.items():
        print(f"  {name}: {count} definitions", file=sys.stderr)
    print(
        "Add a COLLISION_OVERRIDES entry in scripts/postprocess_models.py for each "
        "colliding schema definition, then regenerate.",
        file=sys.stderr,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    ``--models`` and ``--schema`` each carry their own default, so an omitted
    argument resolves to its own default regardless of whether the other one
    was supplied.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Post-process generated models.py: collapse RootModels and rename classes."
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
        help="Path to the source OSCAL schema file (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    models_path: Path = args.models
    schema_path: Path = args.schema

    missing = [path for path in (models_path, schema_path) if not path.exists()]
    if missing:
        for path in missing:
            print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)

    content = models_path.read_text()

    # Phase 1: Collapse scalar RootModels
    content = collapse_scalar_root_models(content)
    content = ensure_annotated_import(content)
    content = fix_email_str_patterns(content)
    content = fix_non_string_patterns(content)

    # Phase 2: Rename wrapper classes using names derived from their own content.
    # Longest key first so a hypothetical Model1/Model10 pair cannot partially match.
    # Guard (Req 3.5): an ambiguous wrapper invalidates the derivation's assumption, so
    # stop on the first one rather than scanning the rest.
    try:
        document_renames = derive_document_renames(content)
    except AmbiguousWrapperError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        print(f"{models_path} was not written", file=sys.stderr)
        sys.exit(1)

    # Guard (Req 3.6): the derived wrappers must account for exactly the document types
    # the schema declares, or a document type has been silently gained or lost.
    expected_documents = count_schema_document_types(schema_path)
    if expected_documents is not None and len(document_renames) != expected_documents:
        report_wrapper_count_mismatch(
            len(document_renames), expected_documents, models_path
        )
        sys.exit(1)

    content = rename_classes(
        content, dict(sorted(document_renames.items(), key=lambda kv: -len(kv[0])))
    )
    # Rename root Model -> OscalDocument (careful not to hit BaseModel etc)
    content = rename_root_model(content)
    # Rename variant classes
    content = rename_classes(content, VARIANT_RENAMES)

    # Phase 3: Strip OscalComplete namespace prefix from all remaining classes
    namespace_renames = build_namespace_renames(schema_path)
    # Also handle numbered variants (e.g. OscalCompleteOscalControlCommonParameter1)
    # by checking what's actually in the content
    numbered_extras: dict[str, str] = {}
    for old_name, new_name in list(namespace_renames.items()):
        for suffix in ("1", "2", "3"):
            variant = old_name + suffix
            if variant in content:
                numbered_extras[variant] = new_name + suffix
    namespace_renames.update(numbered_extras)
    # Skip any that were already renamed by VARIANT_RENAMES
    already_renamed = set(VARIANT_RENAMES.keys())
    namespace_renames = {
        k: v for k, v in namespace_renames.items() if k not in already_renamed
    }
    # Sort by length descending to avoid partial replacements
    sorted_renames = dict(sorted(namespace_renames.items(), key=lambda x: -len(x[0])))
    content = rename_classes(content, sorted_renames)

    # Remove RootModel import if no longer used
    if not re.search(r"\(RootModel\[", content):
        content = re.sub(r"\s*RootModel,?\n?", "\n", content)
        # Clean up import formatting
        content = re.sub(r",\s*\)", "\n)", content)

    # Remove excessive blank lines
    content = re.sub(r"\n{4,}", "\n\n\n", content)

    # Guard: every rename phase is complete, so any duplicated class definition is a
    # collision the overrides missed. Report the full accumulated list and refuse to
    # write rather than emitting a file with duplicate definitions.
    duplicates = find_duplicate_class_definitions(content)
    if duplicates:
        report_collisions(duplicates, models_path)
        sys.exit(1)

    models_path.write_text(content)
    print(f"Post-processed {models_path}")


if __name__ == "__main__":
    main()
