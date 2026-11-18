"""Static-type assertions for the YAML surface on every import path.

`hatch run typing` checks this module. It asserts the resolved return type of
each YAML operation (the eight typed parsers included) through
``oscal_bindings``, ``oscal_bindings.v1``, and
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
from oscal_bindings import (
    AssessmentPlanDocument,
    AssessmentResultsDocument,
    CatalogDocument,
    ComponentDefinitionDocument,
    MappingCollectionDocument,
    OscalDocument,
    PlanOfActionAndMilestonesDocument,
    ProfileDocument,
    SystemSecurityPlanDocument,
)


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

    assert_type(oscal_bindings.parse_catalog_yaml("x: 1"), CatalogDocument)
    assert_type(oscal_bindings.v1.parse_catalog_yaml("x: 1"), CatalogDocument)
    assert_type(oscal_bindings.extensions.parse_catalog_yaml("x: 1"), CatalogDocument)
    assert_type(oscal_bindings.parse_catalog_yaml(b"x: 1"), CatalogDocument)
    assert_type(oscal_bindings.parse_profile_yaml("x: 1"), ProfileDocument)
    assert_type(oscal_bindings.v1.parse_profile_yaml("x: 1"), ProfileDocument)
    assert_type(oscal_bindings.extensions.parse_profile_yaml("x: 1"), ProfileDocument)
    assert_type(oscal_bindings.parse_profile_yaml(b"x: 1"), ProfileDocument)
    assert_type(
        oscal_bindings.parse_component_definition_yaml("x: 1"),
        ComponentDefinitionDocument,
    )
    assert_type(
        oscal_bindings.v1.parse_component_definition_yaml("x: 1"),
        ComponentDefinitionDocument,
    )
    assert_type(
        oscal_bindings.extensions.parse_component_definition_yaml("x: 1"),
        ComponentDefinitionDocument,
    )
    assert_type(
        oscal_bindings.parse_component_definition_yaml(b"x: 1"),
        ComponentDefinitionDocument,
    )
    assert_type(
        oscal_bindings.parse_system_security_plan_yaml("x: 1"),
        SystemSecurityPlanDocument,
    )
    assert_type(
        oscal_bindings.v1.parse_system_security_plan_yaml("x: 1"),
        SystemSecurityPlanDocument,
    )
    assert_type(
        oscal_bindings.extensions.parse_system_security_plan_yaml("x: 1"),
        SystemSecurityPlanDocument,
    )
    assert_type(
        oscal_bindings.parse_system_security_plan_yaml(b"x: 1"),
        SystemSecurityPlanDocument,
    )
    assert_type(
        oscal_bindings.parse_assessment_plan_yaml("x: 1"), AssessmentPlanDocument
    )
    assert_type(
        oscal_bindings.v1.parse_assessment_plan_yaml("x: 1"), AssessmentPlanDocument
    )
    assert_type(
        oscal_bindings.extensions.parse_assessment_plan_yaml("x: 1"),
        AssessmentPlanDocument,
    )
    assert_type(
        oscal_bindings.parse_assessment_plan_yaml(b"x: 1"), AssessmentPlanDocument
    )
    assert_type(
        oscal_bindings.parse_assessment_results_yaml("x: 1"), AssessmentResultsDocument
    )
    assert_type(
        oscal_bindings.v1.parse_assessment_results_yaml("x: 1"),
        AssessmentResultsDocument,
    )
    assert_type(
        oscal_bindings.extensions.parse_assessment_results_yaml("x: 1"),
        AssessmentResultsDocument,
    )
    assert_type(
        oscal_bindings.parse_assessment_results_yaml(b"x: 1"), AssessmentResultsDocument
    )
    assert_type(
        oscal_bindings.parse_plan_of_action_and_milestones_yaml("x: 1"),
        PlanOfActionAndMilestonesDocument,
    )
    assert_type(
        oscal_bindings.v1.parse_plan_of_action_and_milestones_yaml("x: 1"),
        PlanOfActionAndMilestonesDocument,
    )
    assert_type(
        oscal_bindings.extensions.parse_plan_of_action_and_milestones_yaml("x: 1"),
        PlanOfActionAndMilestonesDocument,
    )
    assert_type(
        oscal_bindings.parse_plan_of_action_and_milestones_yaml(b"x: 1"),
        PlanOfActionAndMilestonesDocument,
    )
    assert_type(
        oscal_bindings.parse_mapping_collection_yaml("x: 1"), MappingCollectionDocument
    )
    assert_type(
        oscal_bindings.v1.parse_mapping_collection_yaml("x: 1"),
        MappingCollectionDocument,
    )
    assert_type(
        oscal_bindings.extensions.parse_mapping_collection_yaml("x: 1"),
        MappingCollectionDocument,
    )
    assert_type(
        oscal_bindings.parse_mapping_collection_yaml(b"x: 1"), MappingCollectionDocument
    )
