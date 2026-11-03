"""The traceability record covers the public surface and cites resolvable ids.

The record (`openspec/traceability.json`) holds one entry for each public
operation in `oscal_bindings.v1.__all__`, excluding generated model types, which
``binding-surface`` SRF-001.03 exempts. Each entry cites the contract
requirement(s) that define the operation (SRF-003), and each cited identifier
must resolve in ``openspec/requirements.json`` of the pinned spec artifact
(SRF-004). The record conforms to the store's JSON Schema (SRF-007), which
forbids an entry that mixes a contract identifier with a binding-local
identifier (SRF-007.01).
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema_rs
import pytest
from support.spec_artifact import ensure_spec_artifact

from oscal_bindings import v1
from oscal_bindings.v1 import models

# The record lives in the binding's own openspec directory.
_RECORD_PATH = Path(__file__).resolve().parent.parent / "openspec" / "traceability.json"


def _artifact_openspec() -> Path:
    return ensure_spec_artifact() / "openspec"


def _load_record() -> dict:
    return json.loads(_RECORD_PATH.read_text("utf-8"))


def _index_ids() -> set[str]:
    index = json.loads((_artifact_openspec() / "requirements.json").read_text("utf-8"))
    return {entry["id"] for entry in index["requirements"]}


def _public_operations() -> set[str]:
    """Public names in ``v1.__all__`` that need a record entry.

    A generated model type (and ``DocumentId``, a generated scalar alias) is
    exempt under SRF-001.03: it comes from ``v1.models`` and is governed by the
    model-derivation capability and the naming manifest, not by SRF-003.
    """
    ops: set[str] = set()
    for name in v1.__all__:
        obj = getattr(v1, name)
        generated = hasattr(models, name) and getattr(models, name, None) is obj
        if not generated:
            ops.add(name)
    return ops


def test_record_conforms_to_store_schema() -> None:
    """SRF-007: the record validates against the store's JSON Schema."""
    schema = json.loads(
        (_artifact_openspec() / "traceability.schema.json").read_text("utf-8")
    )
    validator = jsonschema_rs.validator_for(schema)
    errors = list(validator.iter_errors(_load_record()))
    assert not errors, [str(e) for e in errors]


def _missing_entries(record: dict) -> list[str]:
    """Return the public operations that have no entry in ``record``."""
    recorded = {op["name"] for op in record["operations"]}
    return sorted(_public_operations() - recorded)


def _unresolved_identifiers(record: dict) -> list[str]:
    """Return the cited identifiers of ``record`` that the pinned index lacks."""
    ids = _index_ids()
    return [
        req
        for op in record["operations"]
        for req in op.get("requirements", [])
        if req not in ids
    ]


def test_every_public_operation_has_an_entry() -> None:
    """SRF-003.04: a public operation without an entry fails conformance."""
    missing = _missing_entries(_load_record())
    assert not missing, f"public operations without a record entry: {missing}"


def test_no_entry_for_a_name_outside_the_surface() -> None:
    """Each entry names a current public operation, so the record cannot rot."""
    recorded = {op["name"] for op in _load_record()["operations"]}
    extra = sorted(recorded - set(v1.__all__))
    assert not extra, f"record entries not in v1.__all__: {extra}"


def test_each_entry_names_one_public_operation_once() -> None:
    names = [op["name"] for op in _load_record()["operations"]]
    assert len(names) == len(set(names)), "an operation name occurs in two entries"


def test_cited_identifiers_resolve_in_the_pinned_index() -> None:
    """SRF-004: each contract identifier resolves in the requirement index."""
    unresolved = _unresolved_identifiers(_load_record())
    assert not unresolved, f"cited identifiers not in the pinned index: {unresolved}"


def test_yaml_operations_cite_the_contract_requirements() -> None:
    """The three YAML operations cite YML-005, YML-006, YML-008 (proposal item 7)."""
    by_name = {op["name"]: op for op in _load_record()["operations"]}
    assert by_name["parse_oscal_yaml"].get("requirements") == ["YML-005"]
    assert by_name["parse_oscal_yaml_file"].get("requirements") == ["YML-006"]
    assert by_name["serialize_oscal_yaml"].get("requirements") == ["YML-008"]


# --- Guards that the test itself detects each failure (self-verification) ---


def test_detects_a_removed_entry() -> None:
    """Removing an entry for a public operation is caught (SRF-003.04)."""
    record = _load_record()
    record["operations"] = [
        op for op in record["operations"] if op["name"] != "parse_oscal"
    ]
    assert _missing_entries(record) == ["parse_oscal"]


def test_detects_an_unresolvable_identifier() -> None:
    """A cited identifier absent from the index is caught (SRF-004.02)."""
    record = _load_record()
    # A retired/nonexistent identifier of the right shape.
    record["operations"][0]["requirements"].append("MDL-004")
    assert _unresolved_identifiers(record) == ["MDL-004"]


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "x", "requirements": ["PRS-001"], "binding-local": "YRL-001"},
        {"name": "x", "requirements": ["PRS-001.01"]},
        {"name": "x"},
    ],
)
def test_schema_rejects_malformed_entries(entry: dict) -> None:
    """SRF-007: mixed id kinds, a scenario id, and a missing id are all invalid."""
    schema = json.loads(
        (_artifact_openspec() / "traceability.schema.json").read_text("utf-8")
    )
    validator = jsonschema_rs.validator_for(schema)
    bad = {"format": 1, "operations": [entry]}
    assert not validator.is_valid(bad)
