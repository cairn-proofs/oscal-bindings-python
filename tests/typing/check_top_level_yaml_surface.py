"""Static-type assertions for the top-level YAML surface (review finding #5).

`hatch run typing` checks this module. It imports the three YAML operations
through the documented top-level path (`oscal_bindings`, not
`oscal_bindings.v1.extensions`) and asserts their resolved types with
``assert_type``. If the top level re-exported them through a module
``__getattr__`` or a ``globals()`` loop, mypy would see each as ``Any`` and
these assertions would fail, so a regression to that plumbing fails typing.

This module is type-checked, not executed. It never imports PyYAML.
"""

from __future__ import annotations

from pathlib import Path
from typing import assert_type

from oscal_bindings import (
    OscalDocument,
    parse_oscal_yaml,
    parse_oscal_yaml_file,
    serialize_oscal_yaml,
)


def _assert_signatures() -> None:
    doc: OscalDocument = parse_oscal_yaml("catalog: {}")
    assert_type(doc, OscalDocument)
    assert_type(parse_oscal_yaml_file(Path("x.yaml")), OscalDocument)
    assert_type(serialize_oscal_yaml(doc), str)
