"""Tests of scripts/build_docs.py: the Pydantic corrections and the output check."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, Optional

import pdoc.doc
import pytest
from pydantic import Field
from support.scripts import load_script

if TYPE_CHECKING:
    from pathlib import Path

build_docs = load_script("build_docs")


@pytest.fixture(scope="module")
def models() -> pdoc.doc.Module:
    build_docs.apply_corrections()
    import oscal_bindings.v1.models as module

    return pdoc.doc.Module(module)


def test_params_annotation_is_the_plain_type(models: pdoc.doc.Module) -> None:
    params = models.members["Catalog"].members["params"]
    assert params.annotation_str == (
        ": list[oscal_bindings.v1.models.ParameterWithSelect"
        " | oscal_bindings.v1.models.ParameterWithValues] | None"
    )


def test_required_field_has_no_default(models: pdoc.doc.Module) -> None:
    metadata = models.members["Catalog"].members["metadata"]
    assert metadata.default_value_str == ""
    assert models.members["Catalog"].members["params"].default_value_str == ("None")


def test_scalar_alias_shows_its_base_type(models: pdoc.doc.Module) -> None:
    assert models.members["StringDatatype"].default_value_str == "str"


def test_root_model_has_no_pydantic_docstring_or_generic_base(
    models: pdoc.doc.Module,
) -> None:
    document = models.members["OscalDocument"]
    assert document.docstring == ""
    assert not any(base[2].startswith("typing.Generic[") for base in document.bases)


def test_strip_annotated_at_each_depth() -> None:
    nested = Annotated[
        list[Annotated[int | str, Field(description="x")]] | None, Field()
    ]
    assert build_docs.strip_annotated(nested) == list[int | str] | None
    assert build_docs.strip_annotated(Optional[int]) == Optional[int]  # noqa: UP045


def _write(output: Path, name: str, text: str) -> None:
    path = output / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _search_js(*documents: dict[str, str]) -> str:
    """Return a ``search.js`` with a precompiled index of ``documents``."""
    docs = {str(i): d for i, d in enumerate(documents)}
    index = {"documentStore": {"docs": docs, "docInfo": {}}}
    return (
        f"window.pdocSearch = (function(){{ const docs = {json.dumps(index)};\n}})();"
    )


def _clean_output(output: Path) -> None:
    _write(output, "index.html", '<a href="oscal_bindings.html">home</a>')
    _write(
        output,
        "oscal_bindings.html",
        '<h1 id="top">x</h1><a href="oscal_bindings/v1.html#parse_oscal">v1</a>',
    )
    _write(output, "oscal_bindings/v1.html", '<div id="parse_oscal"></div>')
    _write(output, "oscal_bindings/v1/models.html", '<div id="Catalog"></div>')
    _write(
        output,
        "search.js",
        _search_js(
            {"fullname": "oscal_bindings", "modulename": "oscal_bindings"},
            {
                "fullname": "oscal_bindings.v1.parse_oscal",
                "modulename": "oscal_bindings.v1",
            },
        ),
    )


def test_clean_output_has_no_defect(tmp_path: Path) -> None:
    _clean_output(tmp_path)
    assert build_docs.check_output(tmp_path) == []


@pytest.mark.parametrize(
    "forbidden",
    [
        "FieldInfo(annotation=str)",
        "= PydanticUndefined",
        "<function omit_none at 0x10c05d9b0>",
        "RootModel[X]",
        "typing.Generic[~T]",
        "__pydantic_custom_init__",
        "!!! abstract",
        "~oscal_bindings.v1.models.Catalog",
    ],
)
def test_forbidden_string_in_a_page_is_reported(tmp_path: Path, forbidden: str) -> None:
    _clean_output(tmp_path)
    _write(
        tmp_path, "oscal_bindings/v1.html", f'<div id="parse_oscal">{forbidden}</div>'
    )
    defects = build_docs.check_output(tmp_path)
    assert any("oscal_bindings/v1.html: contains" in d for d in defects)


def test_forbidden_string_in_search_is_reported(tmp_path: Path) -> None:
    _clean_output(tmp_path)
    (tmp_path / "search.js").write_text(
        _search_js(
            {"fullname": "oscal_bindings.v1.x", "modulename": "oscal_bindings.v1"}
        )
        + " FieldInfo(",
        encoding="utf-8",
    )
    assert any("search.js: contains" in d for d in build_docs.check_output(tmp_path))


def test_object_on_the_home_page_is_reported(tmp_path: Path) -> None:
    _clean_output(tmp_path)
    _write(
        tmp_path,
        "oscal_bindings.html",
        '<section><div id="parse_oscal" class="function classattr"></div></section>',
    )
    assert "oscal_bindings.html: documents an object" in build_docs.check_output(
        tmp_path
    )


def test_search_index_as_a_list_is_read(tmp_path: Path) -> None:
    _clean_output(tmp_path)
    docs = [{"fullname": "oscal_bindings.parser", "modulename": "oscal_bindings"}]
    (tmp_path / "search.js").write_text(
        f"const docs = {json.dumps(docs)};", encoding="utf-8"
    )
    assert any(
        "is not under oscal_bindings.v1" in d for d in build_docs.check_output(tmp_path)
    )


def test_duplicate_search_entry_is_reported(tmp_path: Path) -> None:
    _clean_output(tmp_path)
    (tmp_path / "search.js").write_text(
        _search_js(
            {
                "fullname": "oscal_bindings.v1.parse_oscal",
                "modulename": "oscal_bindings.v1",
            },
            {
                "fullname": "oscal_bindings.v1.models.parse_oscal",
                "modulename": "oscal_bindings.v1.models",
            },
        ),
        encoding="utf-8",
    )
    assert any(
        "parse_oscal has entries under" in d for d in build_docs.check_output(tmp_path)
    )


def test_search_entry_outside_v1_is_reported(tmp_path: Path) -> None:
    _clean_output(tmp_path)
    (tmp_path / "search.js").write_text(
        _search_js(
            {"fullname": "oscal_bindings.parser", "modulename": "oscal_bindings"}
        ),
        encoding="utf-8",
    )
    assert any(
        "is not under oscal_bindings.v1" in d for d in build_docs.check_output(tmp_path)
    )


def test_dead_links_are_reported(tmp_path: Path) -> None:
    _clean_output(tmp_path)
    _write(
        tmp_path,
        "oscal_bindings/v1.html",
        '<div id="parse_oscal"></div>'
        '<a href="#missing">a</a>'
        '<a href="v1/gone.html">b</a>'
        '<a href="v1/models.html#nope">c</a>'
        '<a href="v1/models.html#Catalog">ok</a>'
        '<a href="https://example.com/x">external</a>'
        '<script>const u = `<a href="${url}">`;</script>',
    )
    defects = build_docs.check_output(tmp_path)
    assert len(defects) == 3
    assert any("'#missing'" in d for d in defects)
    assert any("'v1/gone.html'" in d for d in defects)
    assert any("'v1/models.html#nope'" in d for d in defects)


def test_missing_pages_are_reported(tmp_path: Path) -> None:
    _clean_output(tmp_path)
    (tmp_path / "index.html").unlink()
    (tmp_path / "oscal_bindings/v1/models.html").unlink()
    defects = build_docs.check_output(tmp_path)
    assert "index.html: missing" in defects
    assert "oscal_bindings/v1/models.html: missing" in defects


def test_source_ref_defaults_to_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DOCS_SOURCE_REF", raising=False)
    assert "/blob/main/src/oscal_bindings/" in " ".join(build_docs.pdoc_arguments())
    monkeypatch.setenv("DOCS_SOURCE_REF", "v0.0.0")
    assert "/blob/v0.0.0/src/oscal_bindings/" in " ".join(build_docs.pdoc_arguments())
