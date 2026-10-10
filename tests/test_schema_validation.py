"""Corpus schema validation: default ``model_dump_json()`` is valid OSCAL (2.5).

Every NIST and AWS corpus document is parsed, dumped with an argument-less
``doc.model_dump_json()``, and validated against the vendored OSCAL 1.2.3
complete JSON Schema. One test per document (parametrized at collection), so a
failure names the document.

Validator choices:

- **``jsonschema-rs`` (Draft-07)**, built once per process. It's a compiled
  validator, so it stays fast under coverage tracing; pure-Python
  ``jsonschema`` took ~30 s of CI test time on the 60 MB corpus. Its regex
  engine supports the ``\\p{L}`` / ``\\p{N}`` classes in OSCAL token patterns
  (pinned by `test_negative_control_unicode_pattern_enforced`). Before the
  switch, both validators agreed on every corpus dump and every raw input.
- **``format`` is not asserted** (``validate_formats=False``). The schema uses
  ``date-time``, ``email``, ``uri`` and ``uri-reference``; each sits beside a
  ``pattern`` on the same datatype, which is enforced, and the model fields are
  already ``AwareDatetime`` / ``EmailStr`` / ``AnyUrl``.

Negative controls prove the validator is not vacuous: snake_case keys
(``model_dump(by_alias=False)``), an injected ``null``, and a ``\\p{L}``
pattern must behave as expected.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonschema_rs
import pytest
from support.corpus import AWS_CORPUS, NIST_CORPUS, CorpusDoc, load_corpus_docs

from oscal_bindings import parse_oscal, serialize_oscal

if TYPE_CHECKING:
    from collections.abc import Iterator

SCHEMA_PATH = (
    Path(__file__).parent.parent / "schemas" / "1.2.3" / "oscal_complete_schema.json"
)

#: How many validation errors to show per failing document.
MAX_REPORTED_ERRORS = 5


@functools.cache
def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_bytes())


@functools.cache
def _validator() -> jsonschema_rs.Draft7Validator:
    """The OSCAL schema validator, built once per process."""
    return jsonschema_rs.Draft7Validator(_schema(), validate_formats=False)


def _leaves(error: Any) -> Iterator[Any]:
    """Leaf errors under ``oneOf``/``anyOf`` (the document root is a ``oneOf``)."""
    branches = getattr(error.kind, "context", None)
    if not branches:
        yield error
        return
    for branch in branches:
        for sub in branch:
            yield from _leaves(sub)


def _json_path(path: list[str | int]) -> str:
    return "$" + "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path)


def _schema_errors(instance: Any) -> list[str]:
    """First few validation errors as ``<json path>: <message>`` lines.

    The root ``oneOf`` reports a single error at ``$``; its leaves include
    "wrong document type" noise from the other branches, so the deepest leaves
    (the ones inside the matching branch) are reported first.
    """
    leaves = [
        leaf for error in _validator().iter_errors(instance) for leaf in _leaves(error)
    ]
    leaves.sort(key=lambda e: len(e.instance_path), reverse=True)
    return [
        f"{_json_path(list(e.instance_path))}: {e.message[:300]}"
        for e in leaves[:MAX_REPORTED_ERRORS]
    ]


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
    """A ``null`` value is rejected, and reported at its path."""
    dumped = json.loads(control_doc.model_dump_json())
    dumped["catalog"]["metadata"]["remarks"] = None
    errors = _schema_errors(dumped)
    assert any(e.startswith("$.catalog.metadata.remarks: null") for e in errors), (
        f"null not rejected (or not reported at its path): {errors}"
    )


def test_negative_control_unicode_pattern_enforced() -> None:
    """The ``pattern`` keyword enforces ``\\p{L}`` tokens both ways."""
    token = jsonschema_rs.Draft7Validator(_schema()["definitions"]["TokenDatatype"])
    assert token.is_valid("ünïcode-token"), "\\p{L} token rejected"
    assert not token.is_valid("1-starts-with-digit"), "pattern keyword not enforced"
