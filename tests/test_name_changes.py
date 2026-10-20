"""Tests for ``scripts/name_changes.py``: the release-notes list of name changes.

Unit tests compare tiny synthetic models modules: a unique rename, an ambiguous
one, an enum matched by its values, an inherited field set, and a name that
stays but changes type. One test runs the script against the real repository:
the old ``models.py`` at the merge base of ``HEAD`` and ``main``, and the new one
in the working tree.
"""

from __future__ import annotations

import shutil
import subprocess
import textwrap
from typing import TYPE_CHECKING, Any

import pytest
from support.scripts import load_script

if TYPE_CHECKING:
    from pathlib import Path

name_changes = load_script("name_changes")
spec_artifact = load_script("spec_artifact")


def _definitions(source: str) -> dict[str, Any]:
    return name_changes.read_definitions(textwrap.dedent(source))


def _compare(old: str, new: str) -> Any:
    return name_changes.compare(_definitions(old), _definitions(new))


HEADER = """
from enum import Enum
from typing import Annotated, TypeAlias
from oscal_bindings.v1._base import OscalBaseModel
from pydantic import Field, RootModel
"""


# ---------------------------------------------------------------------------
# read_definitions
# ---------------------------------------------------------------------------


def test_read_definitions_kinds_and_signatures() -> None:
    defs = _definitions(
        HEADER
        + '''
class Algorithm(Enum):
    """The digest method."""
    sha_256 = 'SHA-256'
class Hash(OscalBaseModel):
    """A hash."""
    algorithm: Algorithm
    value: Annotated[str, Field(alias='hash-value')]
class Hashes(RootModel[list[Hash]]):
    root: list[Hash]
class _Private(OscalBaseModel):
    x: int
TokenDatatype = Annotated[str, Field(pattern='^a$')]
Either: TypeAlias = Hash | Hashes
Hash.model_rebuild()
'''
    )
    assert sorted(defs) == ["Algorithm", "Either", "Hash", "Hashes", "TokenDatatype"]
    assert defs["Algorithm"].kind == name_changes.ENUM
    assert defs["Algorithm"].signature == frozenset({"'SHA-256'"})
    assert defs["Hash"].kind == name_changes.MODEL
    assert defs["Hash"].signature == frozenset(
        {"name:algorithm", "name:value", "alias:hash-value"}
    )
    assert defs["Hash"].summary == "A hash."
    assert defs["Hashes"].kind == name_changes.ROOT_MODEL
    assert defs["TokenDatatype"].kind == name_changes.ALIAS
    assert defs["Either"].signature == "Hash | Hashes"


def test_read_definitions_includes_inherited_fields() -> None:
    defs = _definitions(
        HEADER
        + """
class Base(OscalBaseModel):
    a: int
class Child(Base):
    b: int
"""
    )
    assert defs["Child"].kind == name_changes.MODEL
    assert defs["Child"].fields == ("a", "b")


def test_read_definitions_rejects_invalid_python() -> None:
    with pytest.raises(SyntaxError):
        name_changes.read_definitions("class (:\n")


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------


def test_unique_rename_by_field_set() -> None:
    changes = _compare(
        HEADER
        + """
class Hash(OscalBaseModel):
    algorithm: str
    value: str
class Kept(OscalBaseModel):
    k: int
""",
        HEADER
        + """
class BackMatterHash(OscalBaseModel):
    value: str
    algorithm: str
class Kept(OscalBaseModel):
    k: int
""",
    )
    assert changes.renames == {"Hash": "BackMatterHash"}
    assert changes.kept == frozenset({"Kept"})
    assert not changes.unmatched
    assert changes.added_without_predecessor == []


def test_alias_strings_tell_models_apart() -> None:
    changes = _compare(
        HEADER
        + """
class Old(OscalBaseModel):
    href: Annotated[str, Field(alias='href-a')]
""",
        HEADER
        + """
class NewA(OscalBaseModel):
    href: Annotated[str, Field(alias='href-a')]
class NewB(OscalBaseModel):
    href: Annotated[str, Field(alias='href-b')]
""",
    )
    assert changes.renames == {"Old": "NewA"}
    assert changes.added_without_predecessor == ["NewB"]


def test_ambiguous_candidates_are_not_matched() -> None:
    changes = _compare(
        HEADER
        + """
class Link(OscalBaseModel):
    href: str
""",
        HEADER
        + """
class LinkA(OscalBaseModel):
    href: str
class LinkB(OscalBaseModel):
    href: str
""",
    )
    assert changes.renames == {}
    item = changes.unmatched["Link"]
    assert item.candidates == ("LinkA", "LinkB")
    assert item.rivals == ()
    assert changes.added_without_predecessor == ["LinkA", "LinkB"]


def test_two_old_types_for_one_new_type_are_not_matched() -> None:
    changes = _compare(
        HEADER
        + """
class ExternalId(OscalBaseModel):
    id: str
class ExternalId1(ExternalId):
    pass
""",
        HEADER
        + """
class PartyExternalId(OscalBaseModel):
    id: str
""",
    )
    assert changes.renames == {}
    assert changes.unmatched["ExternalId"].candidates == ("PartyExternalId",)
    assert changes.unmatched["ExternalId"].rivals == ("ExternalId1",)


def test_missing_counterpart() -> None:
    changes = _compare(
        HEADER
        + """
class Gone(OscalBaseModel):
    g: int
""",
        HEADER,
    )
    assert changes.removed == frozenset({"Gone"})
    assert changes.unmatched["Gone"].candidates == ()


def test_kind_is_part_of_the_match() -> None:
    changes = _compare(
        HEADER
        + """
class Wrapper(RootModel[list[int]]):
    root: list[int]
""",
        HEADER
        + """
class Plain(OscalBaseModel):
    root: list[int]
""",
    )
    assert changes.renames == {}
    assert changes.unmatched["Wrapper"].candidates == ()


def test_enum_matched_by_member_values() -> None:
    changes = _compare(
        HEADER
        + """
class Algorithm(Enum):
    sha_256 = 'SHA-256'
    sha_512 = 'SHA-512'
class Rel(Enum):
    reference = 'reference'
""",
        HEADER
        + """
class HashAlgorithm(Enum):
    SHA_512 = 'SHA-512'
    SHA_256 = 'SHA-256'
class LinkRel(Enum):
    reference = 'reference'
""",
    )
    assert changes.renames == {"Algorithm": "HashAlgorithm", "Rel": "LinkRel"}


def test_docstring_breaks_a_structural_tie() -> None:
    changes = _compare(
        HEADER
        + '''
class Source(OscalBaseModel):
    """The source."""
    task_uuid: str
class Dependency(OscalBaseModel):
    """The dependency."""
    task_uuid: str
''',
        HEADER
        + '''
class PlaceholderSource(OscalBaseModel):
    """The source."""
    task_uuid: str
class TaskDependency(OscalBaseModel):
    """The dependency."""
    task_uuid: str
''',
    )
    assert changes.renames == {
        "Dependency": "TaskDependency",
        "Source": "PlaceholderSource",
    }


def test_reused_name_with_a_different_type() -> None:
    changes = _compare(
        HEADER
        + '''
class Status(OscalBaseModel):
    """The status of the system component."""
    state: str
class SspStatus(OscalBaseModel):
    """The status of the system."""
    state: str
class Origin(OscalBaseModel):
    """The source of the finding."""
    actors: list[str]
''',
        HEADER
        + '''
class SystemComponentStatus(OscalBaseModel):
    """The status of the system component."""
    state: str
class Status(OscalBaseModel):
    """The status of the system."""
    state: str
class PoamItemOrigin(OscalBaseModel):
    """The source of the finding."""
    actors: list[str]
class Origin(OscalBaseModel):
    """The source of the finding, with tasks."""
    actors: list[str]
    related_tasks: list[str]
''',
    )
    assert changes.reused == frozenset({"Status", "Origin"})
    assert changes.matches == {
        "Status": "SystemComponentStatus",
        "SspStatus": "Status",
        "Origin": "PoamItemOrigin",
    }
    assert changes.renames == {"SspStatus": "Status"}
    assert changes.added_without_predecessor == []


# ---------------------------------------------------------------------------
# render, element types, git guard
# ---------------------------------------------------------------------------


def test_render_sections_and_final_newline() -> None:
    changes = _compare(
        HEADER
        + '''
class Status(OscalBaseModel):
    """Old status."""
    state: str
class Hash(OscalBaseModel):
    value: str
class Gone(OscalBaseModel):
    g: int
''',
        HEADER
        + '''
class Status(OscalBaseModel):
    """New status."""
    state: str
class BackMatterHash(OscalBaseModel):
    value: str
class Fresh(Enum):
    a = 'a'
''',
    )
    text = name_changes.render(
        changes, base="abc", old_elements=["gone", "hash"], new_elements=["fresh"]
    )
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Renamed",
        "## Same name, different type",
        "## Removed",
        "## Added",
        "## Element types",
    ]
    assert "| `Hash` | `BackMatterHash` | model |" in text
    assert '1. Old: model "Old status."; fields: `state`.' in text
    assert "3. New name of the old type: no unique counterpart" in text
    assert "1. `Gone` (model): no new name with the same structure." in text
    assert "1. `Fresh` (enum)." in text
    assert "1. `gone`\n2. `hash`" in text
    # Deterministic: the same input renders the same text.
    assert text == name_changes.render(
        changes, base="abc", old_elements=["hash", "gone"], new_elements=["fresh"]
    )


def test_element_types_from_source_follows_the_selection_rule() -> None:
    source = textwrap.dedent(
        HEADER
        + """
class Algorithm(Enum):
    a = 'a'
class ExternalId(OscalBaseModel):
    id: str
class ExternalId1(ExternalId):
    pass
class Mappings(RootModel[list[int]]):
    root: list[int]
TokenDatatype = Annotated[str, Field()]
"""
    )
    assert name_changes.element_types_from_source(source) == [
        "external-id",
        "external-id1",
        "mappings",
        "root-model",
    ]


@pytest.mark.parametrize("ref", ["", "--output=/tmp/x", "-p"])
def test_old_source_rejects_option_like_refs(ref: str) -> None:
    with pytest.raises(name_changes.NameChangesError, match="invalid git ref"):
        name_changes.old_source(ref)


def test_main_reports_a_git_failure(capsys: pytest.CaptureFixture[str]) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not on PATH")
    status = name_changes.main(["--base", "no-such-ref-for-name-changes"])
    assert status == 1
    assert "failed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The real repository
# ---------------------------------------------------------------------------


def _main_ref_available() -> bool:
    if shutil.which("git") is None:
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "main^{commit}"],  # noqa: S607
        cwd=spec_artifact.REPO_ROOT,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


@pytest.mark.skipif(
    not _main_ref_available(),
    reason="needs git and the `main` ref to read the old models.py",
)
def test_real_repository_document(tmp_path: Path) -> None:
    output = tmp_path / "name-changes.md"
    assert name_changes.main(["--output", str(output)]) == 0
    text = output.read_text(encoding="utf-8")

    reused = text.split("## Same name, different type")[1].split("## Removed")[0]
    for name in ("Status", "Origin", "LocalDefinitions", "MergeFlat"):
        assert f"`{name}`\n" in reused, name
    assert "New name of the old type: `SystemComponentStatus`" in reused
    assert "New name of the old type: `PoamItemOrigin`" in reused

    renamed = text.split("## Renamed")[1].split("## Same name")[0]
    assert "| `Algorithm` | `HashAlgorithm` | enum |" in renamed
    assert "| `Type3` | `DefinedComponentType` | enum |" in renamed
    assert "| `SspStatus` | `Status` | model |" in renamed

    removed_elements = text.split("### Removed element types")[1].split("###")[0]
    assert "`profile-group1`" in removed_elements
