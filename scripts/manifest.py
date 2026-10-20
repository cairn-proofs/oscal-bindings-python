"""Validate the naming manifest of the pinned spec artifact.

The naming manifest, ``names.json``, records the canonical name, the kind, and
the schema sites of each OSCAL type. Generation reads names from it, so it must
reject an invalid manifest before it uses one string of it. ``validate_manifest``
applies these checks in order and returns every failure:

1. ``names.json`` conforms to ``names.schema.json`` of the same artifact. A
   failure here stops the validation, because the later checks assume the
   shape that the JSON Schema defines.
2. ``format`` is a supported format version, and ``oscal-release`` is the
   release of the schema that generation uses.
3. ``schema.sha256`` is the sha256 of the schema bytes that generation reads.
4. The rules that a JSON Schema cannot express: each name is unique, each
   pointer occurs in one entry only and resolves in the schema, each type
   reference names an entry, each union variant property is a property key of
   its branch at every branch site, and each document body field is a property
   key of the wrapper at its site.

The module uses the standard library and ``jsonschema_rs`` only. Run this file
to validate the manifest of the pinned artifact against the vendored schema.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING, Final

import jsonschema_rs
from spec_artifact import (
    OSCAL_RELEASE,
    REPO_ROOT,
    artifact_paths,
    ensure_spec_artifact,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from spec_artifact import ArtifactPaths

# The manifest format versions that this module can read.
SUPPORTED_FORMATS: Final[tuple[int, ...]] = (1,)

# The vendored schema that codegen reads. Its bytes must match schema.sha256.
VENDORED_SCHEMA: Final[Path] = (
    REPO_ROOT / "schemas" / OSCAL_RELEASE / "oscal_complete_schema.json"
)

# The pattern of a canonical name and of a type reference, over the full string.
_NAME: Final = re.compile(r"[A-Z][A-Za-z0-9]*")
# An array index token of RFC 6901: no leading zero, no sign.
_ARRAY_INDEX: Final = re.compile(r"0|[1-9][0-9]*")
# A "~" that does not start one of the escapes "~0" and "~1".
_BAD_ESCAPE: Final = re.compile(r"~(?![01])")


class ManifestError(ValueError):
    """Raised when the naming manifest is invalid.

    ``failures`` holds every failure. The message lists them, one per line.
    """

    def __init__(self, source: str, failures: list[str]) -> None:
        self.failures: list[str] = list(failures)
        lines = "\n".join(f"  {failure}" for failure in self.failures)
        super().__init__(
            f"The naming manifest {source} is invalid "
            f"({len(self.failures)} failures):\n{lines}"
        )


def parse_pointer(pointer: str) -> list[str] | None:
    """Return the reference tokens of a ``#``-fragment JSON pointer.

    The pointer is ``#`` and an RFC 6901 pointer string. ``~1`` decodes to
    ``/`` and ``~0`` to ``~``. Percent-encoding is not allowed. Return ``None``
    for a malformed pointer.
    """
    if not pointer.startswith("#") or "%" in pointer:
        return None
    body = pointer[1:]
    if not body:
        return []
    if not body.startswith("/"):
        return None
    tokens: list[str] = []
    for raw in body[1:].split("/"):
        if _BAD_ESCAPE.search(raw):
            return None
        tokens.append(raw.replace("~1", "/").replace("~0", "~"))
    return tokens


def resolve_pointer(root: object, pointer: str) -> object | None:
    """Return the subschema at ``pointer`` in ``root``, or ``None``.

    The walk uses dict keys and list indexes only, so a token such as
    ``__proto__`` or ``constructor`` resolves only when the JSON holds that key.
    The target must be a JSON object or a boolean, the two forms of a schema.
    """
    tokens = parse_pointer(pointer)
    if tokens is None:
        return None
    node: object = root
    for token in tokens:
        if isinstance(node, list):
            if not _ARRAY_INDEX.fullmatch(token) or int(token) >= len(node):
                return None
            node = node[int(token)]
        elif isinstance(node, dict):
            if token not in node:
                return None
            node = node[token]
        else:
            return None
    return node if isinstance(node, dict | bool) else None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_pointer(path: list[str | int]) -> str:
    return "".join(
        "/" + str(token).replace("~", "~0").replace("/", "~1") for token in path
    )


def _schema_failures(manifest: object, names_schema: dict[str, object]) -> list[str]:
    """Return the JSON Schema errors of ``manifest``, each with its location.

    An error inside an entry also names the entry when the entry has a string
    ``name``.
    """
    validator = jsonschema_rs.validator_for(names_schema)
    types = manifest.get("types") if isinstance(manifest, dict) else None
    failures: list[str] = []
    for error in validator.iter_errors(manifest):
        path = list(error.instance_path)
        where = f"names.json{_json_pointer(path)}"
        if (
            len(path) >= 2  # noqa: PLR2004 - "types" and the entry index
            and path[0] == "types"
            and isinstance(path[1], int)
            and isinstance(types, list)
            and path[1] < len(types)
        ):
            entry = types[path[1]]
            name = entry.get("name") if isinstance(entry, dict) else None
            if isinstance(name, str):
                where += f" (entry {name!r})"
        failures.append(f"[names.schema.json] {where}: {error.message}")
    return failures


def _entries(manifest: dict[str, object]) -> Iterator[dict[str, object]]:
    types = manifest.get("types")
    if isinstance(types, list):
        yield from (entry for entry in types if isinstance(entry, dict))


def _strings(value: object) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _references(entry: dict[str, object]) -> list[str]:
    """Return the type references of ``entry``: members, item, variant types."""
    refs = _strings(entry.get("members"))
    item = entry.get("item")
    if isinstance(item, str):
        refs.append(item)
    refs.extend(
        variant["type"]
        for variant in _variants(entry)
        if isinstance(variant.get("type"), str)
    )
    return refs


def _variants(entry: dict[str, object]) -> list[dict[str, object]]:
    variants = entry.get("variants")
    if isinstance(variants, list):
        return [variant for variant in variants if isinstance(variant, dict)]
    return []


def _has_property(schema: object, site: str, key: str) -> bool:
    node = resolve_pointer(schema, site)
    if not isinstance(node, dict):
        return False
    properties = node.get("properties")
    return isinstance(properties, dict) and key in properties


def _name_and_site_failures(
    manifest: dict[str, object], schema: object, failures: list[str]
) -> dict[str, dict[str, object]]:
    """Check names and pointers. Return the first entry of each valid name."""
    by_name: dict[str, dict[str, object]] = {}
    seen_sites: set[str] = set()
    for entry in _entries(manifest):
        name = entry.get("name")
        if not isinstance(name, str) or not _NAME.fullmatch(name):
            failures.append(
                f"[manifest] the name {name!r} is not a PascalCase identifier"
            )
            continue
        if name in by_name:
            failures.append(f"[manifest] the name {name} occurs more than once")
        by_name.setdefault(name, entry)
        for site in _strings(entry.get("sites")):
            if site in seen_sites:
                failures.append(
                    f"[manifest] the pointer {site} occurs in more than one entry"
                )
            seen_sites.add(site)
            if resolve_pointer(schema, site) is None:
                failures.append(
                    f"[manifest] {name}: the pointer {site} does not resolve"
                )
    return by_name


def _entry_failures(
    name: str,
    entry: dict[str, object],
    by_name: dict[str, dict[str, object]],
    schema: object,
) -> list[str]:
    """Check the type references, variant properties, and body field of an entry."""
    failures: list[str] = []
    for ref in _references(entry):
        if not _NAME.fullmatch(ref):
            failures.append(
                f"{name}: the reference {ref!r} is not a PascalCase identifier"
            )
        elif ref not in by_name:
            failures.append(f"{name}: the reference {ref} names no entry")
    for variant in _variants(entry):
        branch = by_name.get(str(variant.get("type")))
        prop = variant.get("property")
        if branch is None or not isinstance(prop, str):
            continue
        branch_sites = _strings(branch.get("sites"))
        if not all(_has_property(schema, site, prop) for site in branch_sites):
            failures.append(
                f"{name}: {prop} is not a property of the branch {variant.get('type')}"
            )
    body_field = entry.get("body-field")
    if isinstance(body_field, str) and not all(
        _has_property(schema, site, body_field) for site in _strings(entry.get("sites"))
    ):
        failures.append(f"{name}: {body_field} is not a property of the wrapper")
    return [f"[manifest] {failure}" for failure in failures]


def _cross_failures(manifest: dict[str, object], schema: object) -> list[str]:
    """Return the failures of the rules that a JSON Schema cannot express."""
    failures: list[str] = []
    by_name = _name_and_site_failures(manifest, schema, failures)
    for name, entry in by_name.items():
        failures.extend(_entry_failures(name, entry, by_name, schema))
    return failures


def validate_manifest(
    manifest: object,
    names_schema: dict[str, object],
    schema_bytes: bytes,
    release: str,
) -> list[str]:
    """Return every failure of ``manifest``. An empty list means it is valid.

    ``manifest`` is the parsed ``names.json``. ``names_schema`` is the parsed
    ``names.schema.json``. ``schema_bytes`` are the bytes of the complete OSCAL
    schema that codegen reads, and ``release`` is its OSCAL release.
    """
    failures = _schema_failures(manifest, names_schema)
    if failures:
        return failures
    if not isinstance(manifest, dict):
        return ["[manifest] names.json is not a JSON object"]

    fmt = manifest.get("format")
    if isinstance(fmt, bool) or fmt not in SUPPORTED_FORMATS:
        supported = ", ".join(str(f) for f in SUPPORTED_FORMATS)
        failures.append(
            f"[manifest] format {fmt!r} is not supported (supported: {supported})"
        )
    oscal_release = manifest.get("oscal-release")
    if oscal_release != release:
        failures.append(f"[manifest] oscal-release {oscal_release!r} is not {release}")

    schema_info = manifest.get("schema")
    recorded = schema_info.get("sha256") if isinstance(schema_info, dict) else None
    actual = _sha256(schema_bytes)
    if recorded != actual:
        failures.append(
            f"[manifest] schema.sha256 {recorded!r} does not match the schema "
            f"(sha256 {actual})"
        )

    try:
        schema: object = json.loads(schema_bytes)
    except ValueError as exc:
        failures.append(f"[manifest] the schema is not valid JSON: {exc}")
        return failures
    failures.extend(_cross_failures(manifest, schema))
    return failures


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise ManifestError(str(path), [f"cannot read {path.name}: {exc}"]) from exc


def load_validated_manifest(
    paths: ArtifactPaths,
    *,
    schema_path: Path = VENDORED_SCHEMA,
    release: str = OSCAL_RELEASE,
) -> dict[str, object]:
    """Read, validate, and return the manifest of the artifact at ``paths``.

    ``schema_path`` is the complete schema that codegen reads, by default the
    vendored schema. Raise ``ManifestError`` with every failure when a file
    cannot be read or the manifest is invalid.
    """
    manifest = _read_json(paths.names)
    names_schema = _read_json(paths.names_schema)
    if not isinstance(names_schema, dict):
        raise ManifestError(
            str(paths.names_schema), ["names.schema.json is not a JSON object"]
        )
    try:
        schema_bytes = schema_path.read_bytes()
    except OSError as exc:
        raise ManifestError(
            str(paths.names), [f"cannot read the schema {schema_path}: {exc}"]
        ) from exc
    failures = validate_manifest(manifest, names_schema, schema_bytes, release)
    if failures or not isinstance(manifest, dict):
        raise ManifestError(str(paths.names), failures)
    return manifest


def main() -> int:
    """Validate the manifest of the pinned artifact against the vendored schema."""
    paths = artifact_paths(ensure_spec_artifact())
    try:
        manifest = load_validated_manifest(paths)
    except ManifestError as exc:
        print(exc)
        return 1
    types = manifest.get("types")
    count = len(types) if isinstance(types, list) else 0
    print(f"{paths.names}: valid ({count} types)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
