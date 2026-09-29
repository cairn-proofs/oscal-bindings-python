"""Property tests for the codegen post-processor (`scripts/postprocess_models.py`).

Hypothesis-driven counterpart to the example-based coverage in
`tests/test_postprocess.py`. Properties are numbered per the
`major-version-namespace` design document:

- Property 7 — every uncovered class-name collision is reported (below).
- Property 1 — derivation is position-independent (below).
- Property 2 — derivation parity with the positional map (below).

Fixtures here are deliberately module-scoped: Hypothesis's
`function_scoped_fixture` health check fires when a `@given` test pulls a
function-scoped fixture, and reusing one temp directory across examples is safe
because the collision guard refuses to write anything.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import string
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

if TYPE_CHECKING:
    from types import ModuleType

REPO_ROOT = Path(__file__).parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "postprocess_models.py"

#: At least 100 examples per generative property (see the spec's testing strategy).
MAX_EXAMPLES = 100


@pytest.fixture(scope="module")
def pp() -> ModuleType:
    """Load the post-processor script as a module (it lives outside the package)."""
    spec = importlib.util.spec_from_file_location("postprocess_models", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def schema_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A minimal schema so the namespace-rename phase has something to read."""
    path = tmp_path_factory.mktemp("prop_postprocess") / "schema.json"
    path.write_text(
        json.dumps({"definitions": {"oscal-complete-oscal-catalog:catalog": {}}})
    )
    return path


@pytest.fixture(scope="module")
def models_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Scratch generated-source file, rewritten per Hypothesis example."""
    return tmp_path_factory.mktemp("prop_postprocess_models") / "models.py"


# Names the post-processor's own rename phases would rewrite, which would
# invalidate the "the name I injected is the name reported" assertion. The
# generator steers around them rather than the test tolerating them.
_RENAME_SENSITIVE_PREFIXES = ("Model", "OscalComplete")
_RESERVED = frozenset(
    {"BaseModel", "RootModel", "ConfigDict", "Field", "Annotated", "Mappings"}
)


def _is_inert(name: str) -> bool:
    """True when no rename phase in the post-processor will touch `name`."""
    return name not in _RESERVED and not name.startswith(_RENAME_SENSITIVE_PREFIXES)


#: PascalCase-ish class names: an uppercase head plus a lowercase/digit tail.
CLASS_NAMES = st.builds(
    lambda head, tail: head + tail,
    st.sampled_from(string.ascii_uppercase),
    st.text(alphabet=string.ascii_lowercase + string.digits, min_size=3, max_size=8),
).filter(_is_inert)

HEADER = "from __future__ import annotations\n\nfrom pydantic import BaseModel\n"


def _class_block(name: str, field: int) -> str:
    return f"\n\nclass {name}(BaseModel):\n    field_{field}: str\n"


def _synthesize_source(blocks: list[str]) -> str:
    return HEADER + "".join(blocks)


def _reported_collisions(stderr: str) -> dict[str, int]:
    """Parse the guard's report back into the {name: count} map it claims."""
    reported: dict[str, int] = {}
    for line in stderr.splitlines():
        if not line.startswith("  ") or "definitions" not in line:
            continue
        name, _, tail = line.strip().partition(":")
        reported[name] = int(tail.strip().split()[0])
    return reported


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(data=st.data())
def test_all_uncovered_collisions_are_reported(
    data: st.DataObject, pp: ModuleType, models_path: Path, schema_path: Path
) -> None:
    """Feature: major-version-namespace, Property 7: For any generated source
    introducing k uncovered class-name collisions, the Post_Processor exits
    non-zero and its single report names all k of them.

    **Validates: Requirements 7.3**
    """
    # k — how many uncovered collisions this example injects — is itself generated.
    colliding = data.draw(
        st.lists(CLASS_NAMES, min_size=1, max_size=6, unique=True), label="colliding"
    )
    k = len(colliding)
    # How many times each colliding name is defined (>= 2 is what makes it a collision).
    counts = {
        name: data.draw(st.integers(min_value=2, max_value=4), label=f"count[{name}]")
        for name in colliding
    }
    # Singly-defined classes that must NOT show up in the report.
    singletons = [
        name
        for name in data.draw(
            st.lists(CLASS_NAMES, min_size=0, max_size=4, unique=True),
            label="singletons",
        )
        if name not in counts
    ]

    blocks = [
        _class_block(name, field)
        for name, count in counts.items()
        for field in range(count)
    ] + [_class_block(name, 0) for name in singletons]
    # Layout must not matter: duplicates need not be adjacent or in any order.
    blocks = data.draw(st.permutations(blocks), label="layout")

    source = _synthesize_source(blocks)
    models_path.write_text(source)

    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr), pytest.raises(SystemExit) as exc:
        pp.main(["--models", str(models_path), "--schema", str(schema_path)])

    err = stderr.getvalue()
    assert exc.value.code not in (0, None), (
        f"expected non-zero exit, got {exc.value.code!r}"
    )
    # One run produces exactly one report, and it names all k collisions.
    assert err.count("COLLISION_OVERRIDES;") == 1, err
    assert f"{k} class-name collision(s)" in err, err
    assert _reported_collisions(err) == counts, err
    # Refusing to write is part of the contract the report accompanies.
    assert models_path.read_text() == source


# ---------------------------------------------------------------------------
# Property 1 — derivation is position-independent
# ---------------------------------------------------------------------------

#: Mirrors `pp.SCHEMA_DIRECTIVE_FIELD`. Duplicated as a literal so the module-level
#: strategies can steer around it without importing the fixture; the test asserts
#: the two agree, so a rename in the post-processor surfaces here rather than going
#: unnoticed.
SCHEMA_DIRECTIVE_FIELD = "field_schema"

#: snake_case document root keys — one to four lowercase words.
ROOT_KEYS = st.lists(
    st.text(alphabet=string.ascii_lowercase, min_size=2, max_size=6),
    min_size=1,
    max_size=4,
).map("_".join)


def _pascal(root_key: str) -> str:
    return "".join(word.capitalize() for word in root_key.split("_"))


#: Sets of root keys whose derived names are distinct. `unique_by=_pascal` rules out the
#: pairs that would collide after PascalCasing (`a_b` and `ab` both give `AbDocument`),
#: which would otherwise make the name *set* smaller than the wrapper count and blur the
#: invariant being asserted.
ROOT_KEY_SETS = st.lists(
    ROOT_KEYS.filter(lambda key: key != SCHEMA_DIRECTIVE_FIELD),
    min_size=2,
    max_size=8,
    unique_by=_pascal,
)


def _wrapper_block(class_name: str, root_key: str) -> str:
    """A Wrapper_Class as codegen emits it.

    The `$schema` directive plus one body field.
    """
    return (
        f"\n\nclass {class_name}(BaseModel):\n"
        f"    {SCHEMA_DIRECTIVE_FIELD}: str | None = None\n"
        f"    {root_key}: str\n"
    )


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(data=st.data())
def test_derivation_is_position_independent(
    data: st.DataObject, pp: ModuleType
) -> None:
    """Feature: major-version-namespace, Property 1: For any generated model source
    containing a set of Wrapper_Classes, permuting the ordinal suffixes of those class
    names leaves the derived Document_Rename_Map's set of published names unchanged.

    **Validates: Requirements 3.4**
    """
    assert pp.SCHEMA_DIRECTIVE_FIELD == SCHEMA_DIRECTIVE_FIELD

    root_keys = data.draw(ROOT_KEY_SETS, label="root_keys")
    expected = {_pascal(key) + "Document" for key in root_keys}

    # Baseline: ordinals handed out in schema order, exactly as codegen would.
    baseline = pp.derive_document_renames(
        _synthesize_source(
            [
                _wrapper_block(f"Model{i}", key)
                for i, key in enumerate(root_keys, start=1)
            ]
        )
    )

    # The permutation under test: the same wrappers, ordinals shuffled among them — i.e.
    # what a schema revision that reorders the top-level `oneOf` would produce.
    ordinals = data.draw(
        st.permutations(range(1, len(root_keys) + 1)), label="ordinals"
    )
    blocks = [
        _wrapper_block(f"Model{ordinal}", key)
        for ordinal, key in zip(ordinals, root_keys, strict=True)
    ]
    # Source layout must not matter either, independently of the ordinals.
    permuted = pp.derive_document_renames(
        _synthesize_source(data.draw(st.permutations(blocks), label="layout"))
    )

    assert set(baseline.values()) == expected
    assert set(permuted.values()) == expected
    # Stronger than set equality: each wrapper's name follows the body field it carries,
    # so an ordinal that moved takes its published name with it.
    for ordinal, key in zip(ordinals, root_keys, strict=True):
        assert permuted[f"Model{ordinal}"] == _pascal(key) + "Document"


# ---------------------------------------------------------------------------
# Property 2 — parity with the positional map
#
# Example-based on purpose. The input is the single real Active_Schema_Bundle output,
# so there is no input space to sample: the claim is a fixed-point assertion against
# the frozen eight-name positional map. A Hypothesis strategy here would generate
# nothing and only obscure that.
#
# Honesty note: the committed `models.py` is *already* post-processed, so its wrappers
# are named `CatalogDocument`, not `Model1`. Deriving from it cannot reproduce the
# positional map's ordinal *keys*, and asserting that it does would be theater. The
# claim is stated where it is real — at the published-name level — by pairing each
# real wrapper with the snapshot ordinal that published its name, then rewriting the
# headers back to those ordinals and requiring exact equality with the whole map.
# ---------------------------------------------------------------------------


def _wrapper_root_keys(pp: ModuleType, content: str) -> dict[str, str]:
    """Map each Wrapper_Class in `content` to its single Root_Key body field."""
    root_keys: dict[str, str] = {}
    for class_name, body_lines in pp.iter_class_blocks(content):
        fields = pp.class_field_names(body_lines)
        if pp.SCHEMA_DIRECTIVE_FIELD not in fields:
            continue
        body = [f for f in fields if f != pp.SCHEMA_DIRECTIVE_FIELD]
        assert len(body) == 1, f"{class_name} is not an unambiguous wrapper: {body}"
        root_keys[class_name] = body[0]
    return root_keys


class TestProperty2ParityWithPositionalMap:
    """Feature: major-version-namespace, Property 2: For all eight Wrapper_Classes in
    the Active_Schema_Bundle output, the derived published name equals the name the
    positional DOCUMENT_RENAMES map produced.

    **Validates: Requirements 3.7**
    """

    @staticmethod
    def _real_output(pp: ModuleType) -> str:
        return pp.DEFAULT_MODELS_PATH.read_text()

    def test_every_wrapper_publishes_a_name_the_positional_map_published(
        self, pp: ModuleType
    ) -> None:
        """Per-wrapper, not just set-wise: each of the eight names is claimed once."""
        snapshot = pp.POSITIONAL_DOCUMENT_RENAMES_SNAPSHOT
        content = self._real_output(pp)
        derived = pp.derive_document_renames(content)
        root_keys = _wrapper_root_keys(pp, content)

        assert len(derived) == 8 == len(snapshot)
        assert set(derived) == set(root_keys)

        # The name each wrapper publishes, keyed by the Root_Key it carries. Pairing on
        # content rather than ordinal is the whole point: the positional map's ordinals
        # are gone, its published names are what must survive.
        published_by_root_key = {root_keys[cls]: name for cls, name in derived.items()}
        assert len(published_by_root_key) == 8, "two wrappers share a Root_Key"

        unclaimed = set(snapshot.values())
        for root_key, published in published_by_root_key.items():
            assert published in unclaimed, (
                f"{root_key!r} published {published!r}, which the positional map "
                f"never produced (remaining: {sorted(unclaimed)})"
            )
            unclaimed.remove(published)
        assert not unclaimed, (
            f"positional names no wrapper published: {sorted(unclaimed)}"
        )

    def test_restoring_the_snapshots_ordinals_reproduces_the_map_exactly(
        self, pp: ModuleType
    ) -> None:
        """The strongest form of parity available on post-processed output.

        Give each real wrapper back the ordinal under which the positional map published
        its name — rewriting only the class *header*, which is all the derivation reads,
        so the bodies keep the real bundle's Root_Keys — and the derivation must
        reproduce the positional map whole, keys and values.

        What this actually checks is the substantive part of Req 3.7: that the wrapper
        the positional map called `Model1` is in fact the one carrying `catalog`, and so
        on for all eight. The ordinals come from the snapshot; the Root_Keys do not.
        """
        snapshot = pp.POSITIONAL_DOCUMENT_RENAMES_SNAPSHOT
        content = self._real_output(pp)
        ordinal_of = {name: ordinal for ordinal, name in snapshot.items()}

        for published, ordinal in ordinal_of.items():
            header = f"class {published}(BaseModel):"
            assert header in content, f"expected wrapper header for {published}"
            content = content.replace(header, f"class {ordinal}(BaseModel):")

        assert pp.derive_document_renames(content) == snapshot
