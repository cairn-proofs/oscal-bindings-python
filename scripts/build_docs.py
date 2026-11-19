"""Build the API docs with pdoc, and fail when the output has a known defect.

``hatch run docs`` runs this script. It corrects the way pdoc shows the
generated Pydantic models, calls the pdoc command line, and then checks the
output files. See design D1 and D4 of the OpenSpec change ``publish-api-docs``
and the "API docs" section of DEVELOPING.md.

Set ``DOCS_SOURCE_REF`` to the commit or the tag that the source links point
to. The default is ``main``.
"""

from __future__ import annotations

import functools
import html.parser
import json
import operator
import os
import sys
import types
from pathlib import Path
from typing import Annotated, Any, Union, get_args, get_origin
from urllib.parse import unquote, urldefrag, urlparse

import pdoc.__main__
import pdoc.doc
import pdoc.doc_types
import pdoc.render
from pdoc._compat import formatannotation
from pydantic import BaseModel
from pydantic_core import PydanticUndefined

import oscal_bindings.v1

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "docs" / "pdoc-templates"
OUTPUT_DIR = ROOT / "build" / "api-docs"
REPO_BLOB_URL = "https://github.com/cairn-proofs/oscal-bindings-python/blob"
PAGE_MODULES = ("oscal_bindings", "oscal_bindings.v1", "oscal_bindings.v1.models")

# Strings that must not appear in an HTML page or in the search index.
FORBIDDEN_STRINGS = (
    "FieldInfo(",
    "PydanticUndefined",
    "at 0x",
    "RootModel[",
    "Generic[~",
    "__pydantic_",
    "!!! ",
    "~oscal_bindings",
)


def strip_annotated(annotation: Any) -> Any:
    """Return ``annotation`` without each ``Annotated`` wrapper, at each depth."""
    origin = get_origin(annotation)
    if origin is Annotated:
        return strip_annotated(get_args(annotation)[0])
    args = get_args(annotation)
    if origin is None or not args:
        return annotation
    stripped = tuple(strip_annotated(arg) for arg in args)
    if stripped == args:
        return annotation
    try:
        if origin is Union or origin is types.UnionType:
            return functools.reduce(operator.or_, stripped)
        return origin[stripped]
    except TypeError:
        return annotation


def _is_scalar_alias(variable: pdoc.doc.Variable) -> bool:
    return (
        variable.annotation is pdoc.doc_types.empty
        and get_origin(variable.default_value) is Annotated
    )


def _format(annotation: Any) -> str:
    """Format ``annotation`` as pdoc does, without ``Annotated`` wrappers."""
    formatted = formatannotation(strip_annotated(annotation))
    return pdoc.doc._remove_collections_abc(formatted)  # noqa: SLF001


def apply_corrections() -> None:
    """Correct the Pydantic output of the classes of ``pdoc.doc`` (design D4)."""
    variable = pdoc.doc.Variable
    class_ = pdoc.doc.Class
    if getattr(variable, "_oscal_corrected", False):
        return
    original_annotation = variable.annotation_str
    original_default = variable.default_value_str
    original_docstring = class_.docstring
    original_bases = class_.bases

    def annotation_str(self: pdoc.doc.Variable) -> str:
        if self.annotation is pdoc.doc_types.empty:
            return str(original_annotation.func(self))
        return f": {_format(self.annotation)}"

    def default_value_str(self: pdoc.doc.Variable) -> str:
        if self.default_value is PydanticUndefined:
            return ""
        if _is_scalar_alias(self):
            return _format(self.default_value)
        return str(original_default.func(self))

    def docstring(self: pdoc.doc.Class) -> str:
        cls = self.obj
        if (
            isinstance(cls, type)
            and issubclass(cls, BaseModel)
            and not cls.__dict__.get("__doc__")
        ):
            return ""
        return str(original_docstring.func(self))

    def bases(self: pdoc.doc.Class) -> list[tuple[str, str, str]]:
        return [
            base
            for base in original_bases.func(self)
            if not base[2].startswith("typing.Generic[")
        ]

    variable.annotation_str = functools.cached_property(annotation_str)  # type: ignore[misc,assignment]
    variable.annotation_str.__set_name__(variable, "annotation_str")
    variable.default_value_str = functools.cached_property(default_value_str)  # type: ignore[misc,assignment]
    variable.default_value_str.__set_name__(variable, "default_value_str")
    class_.docstring = functools.cached_property(docstring)  # type: ignore[misc,assignment]
    class_.docstring.__set_name__(class_, "docstring")
    class_.bases = functools.cached_property(bases)  # type: ignore[misc,assignment]
    class_.bases.__set_name__(class_, "bases")
    variable._oscal_corrected = True  # type: ignore[attr-defined]  # noqa: SLF001


class _PageParser(html.parser.HTMLParser):
    """Collect the ids, the links, and the member entries of one HTML page."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.entries = 0
        self._script_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self._script_depth += 1
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.add(str(attributes["id"]))
        if tag == "a" and attributes.get("href") and not self._script_depth:
            self.links.append(str(attributes["href"]))
        if "classattr" in str(attributes.get("class") or "").split():
            self.entries += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._script_depth -= 1


def _search_documents(search_js: str) -> list[dict[str, Any]]:
    """Return the documents of the search index of ``search.js``.

    pdoc writes the index as a list, or, when Node.js is present, as a
    precompiled Elasticlunr index whose documents are in ``documentStore``.
    """
    marker = "const docs = "
    start = search_js.index(marker) + len(marker)
    index, _ = json.JSONDecoder().raw_decode(search_js[start:])
    if isinstance(index, list):
        return index
    return list(index["documentStore"]["docs"].values())


def check_output(output: Path) -> list[str]:
    """Return one line for each defect that the pdoc output in ``output`` has."""
    defects: list[str] = []
    pages: dict[str, _PageParser] = {}
    for path in sorted(output.rglob("*.html")):
        parser = _PageParser()
        text = path.read_text(encoding="utf-8")
        parser.feed(text)
        pages[path.relative_to(output).as_posix()] = parser
        defects.extend(
            f"{path.relative_to(output).as_posix()}: contains {forbidden!r}"
            for forbidden in FORBIDDEN_STRINGS
            if forbidden in text
        )
    search_path = output / "search.js"
    search_text = (
        search_path.read_text(encoding="utf-8") if search_path.exists() else ""
    )
    defects.extend(
        f"search.js: contains {forbidden!r}"
        for forbidden in FORBIDDEN_STRINGS
        if forbidden in search_text
    )
    defects.extend(
        f"{required}: missing"
        for required in ("index.html", "oscal_bindings/v1/models.html")
        if required not in pages
    )
    if "oscal_bindings.html" in pages and pages["oscal_bindings.html"].entries:
        defects.append("oscal_bindings.html: documents an object")
    if search_text:
        owners: dict[str, set[str]] = {}
        for document in _search_documents(search_text):
            fullname = str(document.get("fullname", ""))
            module = str(document.get("modulename", ""))
            if fullname != "oscal_bindings" and not fullname.startswith(
                "oscal_bindings.v1"
            ):
                defects.append(f"search.js: {fullname} is not under oscal_bindings.v1")
            qualname = fullname[len(module) + 1 :] if module else ""
            if qualname and fullname.startswith(f"{module}."):
                owners.setdefault(qualname, set()).add(module)
        defects.extend(
            f"search.js: {name} has entries under {sorted(modules)}"
            for name, modules in sorted(owners.items())
            if len(modules) > 1
        )
    for name, page in sorted(pages.items()):
        for link in page.links:
            parsed = urlparse(link)
            if parsed.scheme or parsed.netloc:
                continue
            target_ref, fragment = urldefrag(link)
            target = (
                name
                if not target_ref
                else ((Path(name).parent / unquote(target_ref)).as_posix())
            )
            target = os.path.normpath(target).replace(os.sep, "/")
            if target not in pages:
                defects.append(
                    f"{name}: link {link!r} goes to a page that does not exist"
                )
            elif fragment and unquote(fragment) not in pages[target].ids:
                defects.append(
                    f"{name}: link {link!r} goes to an id that does not exist"
                )
    return defects


def source_ref() -> str:
    """Return the ref of the source links: ``DOCS_SOURCE_REF``, or ``main``."""
    return os.environ.get("DOCS_SOURCE_REF") or "main"


def pdoc_arguments(output: Path = OUTPUT_DIR) -> list[str]:
    """Return the arguments of the pdoc command line (design D1)."""
    edit_url = f"oscal_bindings={REPO_BLOB_URL}/{source_ref()}/src/oscal_bindings/"
    return [
        "-d",
        "google",
        "-t",
        str(TEMPLATE_DIR),
        "-e",
        edit_url,
        *PAGE_MODULES,
        "-o",
        str(output),
    ]


def main() -> int:
    """Build the docs, check them, and return the exit code."""
    apply_corrections()
    pdoc.render.env.globals["v1_public_names"] = sorted(oscal_bindings.v1.__all__)
    pdoc.__main__.cli(pdoc_arguments())
    defects = check_output(OUTPUT_DIR)
    for defect in defects:
        print(f"build_docs: {defect}", file=sys.stderr)
    return 1 if defects else 0


if __name__ == "__main__":
    raise SystemExit(main())
