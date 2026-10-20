"""Property tests for the codegen post-processor (`scripts/postprocess_models.py`).

Hypothesis-driven counterpart to the example-based coverage in
`tests/test_postprocess.py`:

1. An inline union of exactly the variant set becomes the alias name, in any
   order of the names and with or without ``None``. Any other set stays.
2. The guards list every offender: each missing manifest name, each class
   outside the manifest, and each duplicate name with its count.
"""

from __future__ import annotations

import re
import string
from typing import TYPE_CHECKING, Any

from hypothesis import given, settings
from hypothesis import strategies as st
from support.scripts import load_script

if TYPE_CHECKING:
    from types import ModuleType

pp: ModuleType = load_script("postprocess_models")

#: At least 100 examples per generative property.
MAX_EXAMPLES = 100

#: PascalCase class names: an uppercase head plus a lowercase/digit tail.
CLASS_NAMES = st.builds(
    lambda head, tail: head + tail,
    st.sampled_from(string.ascii_uppercase),
    st.text(alphabet=string.ascii_lowercase + string.digits, min_size=3, max_size=8),
).filter(lambda name: name not in {"None", "True", "False"})

HEADER = "from __future__ import annotations\n\nfrom pydantic import BaseModel\n"


def _class_block(name: str, field: int) -> str:
    return f"\n\nclass {name}(BaseModel):\n    field_{field}: str\n"


def _manifest(names: list[str]) -> dict[str, Any]:
    return {"types": [{"name": name, "kind": "object"} for name in names]}


# ---------------------------------------------------------------------------
# Property 1: inline unions
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(data=st.data())
def test_inline_union_of_the_variant_set_becomes_the_alias(data: st.DataObject) -> None:
    variants = data.draw(
        st.lists(CLASS_NAMES, min_size=2, max_size=4, unique=True), label="variants"
    )
    order = data.draw(st.permutations(variants), label="order")
    nullable = data.draw(st.booleans(), label="nullable")
    # Black writes a long union over several lines, with "|" at each line start.
    separator = data.draw(st.sampled_from([" | ", "\n        | "]), label="sep")
    union = separator.join([*order, *(["None"] if nullable else [])])
    source = f"x: Annotated[\n    list[{union}],\n    Field(min_length=1),\n]\n"

    result = pp.replace_inline_unions(source, {"Alias": variants})

    expected = "Alias | None" if nullable else "Alias"
    assert (
        result == f"x: Annotated[\n    list[{expected}],\n    Field(min_length=1),\n]\n"
    )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(data=st.data())
def test_inline_union_of_another_set_stays(data: st.DataObject) -> None:
    names = data.draw(
        st.lists(CLASS_NAMES, min_size=3, max_size=5, unique=True), label="names"
    )
    variants = names[:2]
    # A strict subset or a strict superset of the variants, never the set itself.
    other = data.draw(
        st.sampled_from([[variants[0], *names[2:]], [*variants, *names[2:]]]),
        label="other",
    )
    source = f"x: {' | '.join(other)} | None = None\n"
    assert pp.replace_inline_unions(source, {"Alias": variants}) == source


# ---------------------------------------------------------------------------
# Property 2: the guards list every offender
# ---------------------------------------------------------------------------


def _reported_duplicates(failures: list[str]) -> dict[str, int]:
    reported: dict[str, int] = {}
    for failure in failures:
        match = re.match(r"\[guard 3\] (\w+) is defined (\d+) times", failure)
        if match:
            reported[match.group(1)] = int(match.group(2))
    return reported


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(data=st.data())
def test_every_duplicate_name_is_reported(data: st.DataObject) -> None:
    names = data.draw(
        st.lists(CLASS_NAMES, min_size=1, max_size=8, unique=True), label="names"
    )
    duplicated = data.draw(
        st.lists(st.sampled_from(names), min_size=1, unique=True), label="duplicated"
    )
    counts = {
        name: data.draw(st.integers(min_value=2, max_value=4), label=f"count[{name}]")
        for name in duplicated
    }
    blocks = [
        _class_block(name, field)
        for name in names
        for field in range(counts.get(name, 1))
    ]
    # Layout must not matter: duplicates need not be adjacent or in any order.
    blocks = data.draw(st.permutations(blocks), label="layout")

    failures = pp.guard_failures(HEADER + "".join(blocks), _manifest(names))

    assert _reported_duplicates(failures) == counts
    assert all(f.startswith("[guard 3]") for f in failures), failures


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(data=st.data())
def test_every_missing_and_every_stray_name_is_reported(data: st.DataObject) -> None:
    names = data.draw(
        st.lists(CLASS_NAMES, min_size=2, max_size=10, unique=True), label="names"
    )
    split = data.draw(st.integers(min_value=0, max_value=len(names)), label="split")
    stray_split = data.draw(
        st.integers(min_value=split, max_value=len(names)), label="stray"
    )
    # names[:split] are defined and in the manifest, names[split:stray_split] are
    # defined and not in the manifest, and the rest are in the manifest only.
    defined = names[:stray_split]
    in_manifest = names[:split] + names[stray_split:]
    source = HEADER + "".join(_class_block(name, 0) for name in defined)

    failures = pp.guard_failures(source, _manifest(in_manifest))

    missing = {
        m.group(1)
        for f in failures
        if (m := re.match(r"\[guard 1\] the manifest name (\w+) ", f))
    }
    stray = {m.group(1) for f in failures if (m := re.match(r"\[guard 2\] (\w+) ", f))}
    assert missing == set(names[stray_split:])
    assert stray == set(names[split:stray_split])
    assert len(failures) == len(missing) + len(stray)
