"""Corpus schema validation: default ``model_dump_json()`` is valid OSCAL (2.5).

Every NIST and AWS corpus document is parsed, dumped with an argument-less
``doc.model_dump_json()``, and validated against the vendored OSCAL 1.2.3
complete JSON Schema. One test per document (parametrized at collection), so a
failure names the document and the xdist workers share the load.

Validator choices:

- **Draft-07** (the schema's ``$schema``), built once per process and reused.
- **``pattern`` via the ``regex`` module.** OSCAL token patterns use ``\\p{L}``
  / ``\\p{N}``, which stdlib ``re`` rejects. The stock keyword is replaced via
  ``jsonschema.validators.extend``; compiled patterns are cached. The schema has
  no ``patternProperties`` or ``propertyNames``, so ``pattern`` is the only
  regex-bearing keyword. Python's ``$`` also matches before a trailing newline,
  unlike ECMA-262; that only makes this check slightly more permissive.
- **``format`` is not asserted** (jsonschema's default: annotation only). The
  schema uses ``date-time``, ``email``, ``uri`` and ``uri-reference``. Each
  ``format`` sits beside a ``pattern`` on the same datatype, which is enforced,
  and the model fields are already ``AwareDatetime`` / ``EmailStr`` /
  ``AnyUrl``. jsonschema's ``uri`` checkers need optional packages
  (``rfc3987``) that aren't installed, so enabling ``format_checker`` would
  silently skip them anyway.

A negative control proves the validator is not vacuous: snake_case keys
(``model_dump(by_alias=False)``) and an injected ``null`` must both fail.
"""

from __future__ import annotations

import copy
import functools
import itertools
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import regex
from jsonschema import Draft7Validator, ValidationError, validators
from support.corpus import AWS_CORPUS, NIST_CORPUS, CorpusDoc, load_corpus_docs

from oscal_bindings import parse_oscal, serialize_oscal

if TYPE_CHECKING:
    from collections.abc import Iterator

    from jsonschema.protocols import Validator

SCHEMA_PATH = (
    Path(__file__).parent.parent / "schemas" / "1.2.3" / "oscal_complete_schema.json"
)

#: How many validation errors to show per failing document.
MAX_REPORTED_ERRORS = 5


@functools.cache
def _compile(pattern: str) -> regex.Pattern[str]:
    return regex.compile(pattern)


def _pattern(
    validator: Validator, pattern: str, instance: Any, _schema: dict[str, Any]
) -> Iterator[ValidationError]:
    """``pattern`` keyword backed by ``regex`` (supports ``\\p{..}`` classes)."""
    if validator.is_type(instance, "string") and not _compile(pattern).search(instance):
        yield ValidationError(f"{instance!r} does not match {pattern!r}")


_OscalDraft7Validator = validators.extend(Draft7Validator, {"pattern": _pattern})


@functools.cache
def _validator() -> Validator:
    """The OSCAL schema validator, built once per process."""
    schema = json.loads(SCHEMA_PATH.read_bytes())
    # check_schema() checks the metaschema's ``format: regex`` with stdlib
    # ``re``, which rejects ``\p{L}``; check it with ``regex`` instead.
    checker = copy.deepcopy(Draft7Validator.FORMAT_CHECKER)
    checker.checks("regex", raises=regex.error)(regex.compile)
    Draft7Validator(Draft7Validator.META_SCHEMA, format_checker=checker).validate(
        schema
    )
    return _OscalDraft7Validator(schema)


def _leaves(error: ValidationError) -> Iterator[ValidationError]:
    """Leaf errors under ``oneOf``/``anyOf`` (the document root is a ``oneOf``)."""
    if not error.context:
        yield error
    for sub in error.context or ():
        yield from _leaves(sub)


def _schema_errors(instance: Any) -> list[str]:
    """First few validation errors as ``<json path>: <message>`` lines.

    The root ``oneOf`` reports a single error at ``$``; its leaves include
    "wrong document type" noise from the other branches, so the deepest leaves
    (the ones inside the matching branch) are reported first.
    """
    errors = itertools.islice(_validator().iter_errors(instance), MAX_REPORTED_ERRORS)
    leaves = [leaf for error in errors for leaf in _leaves(error)]
    leaves.sort(key=lambda e: len(e.absolute_path), reverse=True)
    return [f"{e.json_path}: {e.message[:300]}" for e in leaves[:MAX_REPORTED_ERRORS]]


def _corpus_docs() -> list[CorpusDoc]:
    docs = [*load_corpus_docs(NIST_CORPUS), *load_corpus_docs(AWS_CORPUS)]
    assert docs, "corpus is empty — cannot validate (fail-loud, Req 5.4)"
    return docs


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrize ``corpus_doc`` over every NIST and AWS document (not sampled)."""
    if "corpus_doc" in metafunc.fixturenames:
        docs = _corpus_docs()
        metafunc.parametrize(
            "corpus_doc",
            docs,
            ids=[f"{d.corpus_name.split()[0]}:{d.rel_path}" for d in docs],
        )


def test_default_model_dump_json_is_schema_valid(corpus_doc: CorpusDoc) -> None:
    """Argument-less ``model_dump_json()`` validates against the OSCAL schema.

    **Validates: Requirements 2.5**
    """
    where = f"{corpus_doc.corpus_name}:{corpus_doc.rel_path}"
    doc = parse_oscal(corpus_doc.raw_bytes)
    errors = _schema_errors(json.loads(doc.model_dump_json()))
    if errors:
        # Triage context: does the explicit serializer or the raw input fail too?
        serialized_ok = not _schema_errors(json.loads(serialize_oscal(doc)))
        input_ok = not _schema_errors(json.loads(corpus_doc.raw_bytes))
        pytest.fail(
            f"{where}: default model_dump_json() is not schema-valid "
            f"(serialize_oscal valid: {serialized_ok}; raw input valid: "
            f"{input_ok}). First errors:\n  " + "\n  ".join(errors)
        )


@pytest.fixture(scope="module")
def control_doc() -> Any:
    """A small schema-valid corpus catalog for the negative controls."""
    catalogs = [d for d in load_corpus_docs(NIST_CORPUS) if d.root_key == "catalog"]
    assert catalogs, "no NIST catalog in corpus"
    smallest = min(catalogs, key=lambda d: len(d.raw_bytes))
    doc = parse_oscal(smallest.raw_bytes)
    assert not _schema_errors(json.loads(doc.model_dump_json())), (
        f"control doc {smallest.rel_path} must be valid for the controls to mean much"
    )
    return doc


def test_negative_control_snake_case_keys_fail(control_doc: Any) -> None:
    """Python field names (``oscal_version``, ``last_modified``) are rejected."""
    dumped = control_doc.model_dump(mode="json", by_alias=False)
    assert "oscal_version" in json.dumps(dumped), "control has no snake_case key"
    assert _schema_errors(dumped), "validator accepted snake_case keys"


def test_negative_control_injected_null_fails(control_doc: Any) -> None:
    """A ``null`` value is rejected."""
    dumped = json.loads(control_doc.model_dump_json())
    dumped["catalog"]["metadata"]["remarks"] = None
    errors = _schema_errors(dumped)
    assert any(e.startswith("$.catalog.metadata.remarks: None") for e in errors), (
        f"null not rejected (or not reported at its path): {errors}"
    )


def test_negative_control_unicode_pattern_enforced() -> None:
    """The ``regex``-backed ``pattern`` enforces ``\\p{L}`` tokens both ways."""
    token = _OscalDraft7Validator(_validator().schema["definitions"]["TokenDatatype"])
    assert token.is_valid("ünïcode-token"), "\\p{L} token rejected"
    assert not token.is_valid("1-starts-with-digit"), "pattern keyword not enforced"
