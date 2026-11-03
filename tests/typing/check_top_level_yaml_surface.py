"""Static-type assertions for the YAML surface on every import path.

`hatch run typing` checks this module. It asserts the resolved return type of
each YAML operation through ``oscal_bindings``, ``oscal_bindings.v1``, and
``oscal_bindings.extensions`` with ``assert_type``. Each assertion takes the
call expression itself, so a re-export that a type checker sees as ``Any``
(a module ``__getattr__`` or a ``globals()`` loop) fails the check.

This module is type-checked, not executed. It never imports PyYAML.
"""

from __future__ import annotations

from pathlib import Path
from typing import assert_type

import oscal_bindings
import oscal_bindings.extensions
import oscal_bindings.v1
from oscal_bindings import OscalDocument


def _assert_signatures(doc: OscalDocument) -> None:
    assert_type(oscal_bindings.parse_oscal_yaml("catalog: {}"), OscalDocument)
    assert_type(oscal_bindings.parse_oscal_yaml(b"catalog: {}"), OscalDocument)
    assert_type(oscal_bindings.parse_oscal_yaml_file(Path("x.yaml")), OscalDocument)
    assert_type(oscal_bindings.serialize_oscal_yaml(doc), str)

    assert_type(oscal_bindings.v1.parse_oscal_yaml("catalog: {}"), OscalDocument)
    assert_type(oscal_bindings.v1.parse_oscal_yaml_file("x.yaml"), OscalDocument)
    assert_type(oscal_bindings.v1.serialize_oscal_yaml(doc), str)

    assert_type(
        oscal_bindings.extensions.parse_oscal_yaml("catalog: {}"), OscalDocument
    )
    assert_type(
        oscal_bindings.extensions.parse_oscal_yaml_file("x.yaml"), OscalDocument
    )
    assert_type(oscal_bindings.extensions.serialize_oscal_yaml(doc), str)
