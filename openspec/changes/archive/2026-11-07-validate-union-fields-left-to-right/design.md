# Design

## Context

See [proposal.md - Why](proposal.md#why) for the motivation. These facts constrain the approach.

1. `add_union_aliases` in `scripts/postprocess_models.py` emits each `union` entry of the manifest as
   `Name: TypeAlias = A | B`. `replace_inline_unions` replaces each inline union of exactly a variant set with the
   alias name. Codegen never writes an alias name itself, so each use of an alias in a field comes from
   `replace_inline_unions`.
2. In all 13 unions, the manifest property of each variant is a field of that variant only. Thus a value with a
   variant property validates as that variant only, and a value with no variant property validates as each variant
   that has no required property. Smart mode then picks the first one in manifest order.
   `test_union_alias_selects_each_variant`, `test_union_alias_rejects_the_combination_of_variants`, and
   `test_union_without_a_variant_property_selects_the_first_variant` in `tests/test_models_manifest.py` pin these
   facts for each later manifest.
3. A plain union alias is a `types.UnionType`, so `isinstance(value, CatalogGroup)` works. An `Annotated` alias raises
   `TypeError` in `isinstance`.
4. A probe compared three scratch copies of the models, with GC disabled, as the median of 9 runs (one parse for the
   catalog, batches of 200 for the other documents):

   | Document | Today | `left_to_right` | Callable discriminator |
   |---|---|---|---|
   | 800-53 rev5 catalog, 10.4 MB | 55.5 to 56.5 ms | 45.7 to 46.3 ms | 54.4 to 56.5 ms |
   | 800-53 rev4 HIGH profile, 61 KB | 379 to 384 µs | 355 µs | 353 to 357 µs |
   | SSP example, 22 KB | 96 to 97 µs | 94 to 95 µs | 96 µs |
   | AWS RDS component definition, 120 KB | 575 to 578 µs | 571 to 574 µs | 577 to 578 µs |
   | Assessment results example, 14 KB | 53 to 54 µs | 49 to 50 µs | 51 µs |

   The corpora hold no other large document. The largest profile, SSP, and component definition are 22 to 120 KB.

## Goals / Non-Goals

**Goals:**

1. Parse the 800-53 rev5 catalog at least 10% faster, as the GC-off median of `parse_oscal(bytes)`.
2. Parse no other document type slower: the profile, the SSP, the component definition, and the assessment results
   of Context item 4 stay within 5% of today.
3. Parse each valid document to the same model, and report the same error entries for each invalid one.

**Non-Goals:**

1. Fewer error entries for a fault inside a union value (cairn-proofs/oscal-bindings-specs#36).
2. A timing test in CI. The suite runs on four Pythons under xdist, so a time limit would fail at random.
3. A change to a direct use of an alias, such as `TypeAdapter(CatalogGroup)`.

## Decisions

### D1: `union_mode='left_to_right'` at each union field

`replace_inline_unions` gets an optional `wrap` argument, a format string. With it, the function writes
`Annotated[CatalogGroup, Field(union_mode='left_to_right')]` in place of the inline union, and `| None` stays outside.
Without it, the function behaves as today, so its property tests stay as they are. `add_union_aliases` passes the
argument. `Field` and `Annotated` are imported already.

`left_to_right` tries the variants in manifest order and returns the first that validates. By Context item 2, that is
the variant that smart mode picks for each valid value. The probe confirmed the same variant at each union site. It
also confirmed the same error entries for each of 16 inputs. These are the 12 invalid JSON inputs of the
spec-artifact corpus and 4 faults in union values of the 800-53 catalog.

Alternative: a callable `Discriminator` on the variant property, at each field. It also selects one variant, and it
reports one error entry for a fault inside a union value. But the callable runs in Python for each union value, and
the probe measured no gain on the catalog (Context item 4). It also needs a helper in `_base.py` and new guards.

Alternative: `left_to_right` on the alias itself. One annotation for each alias, but `isinstance(value, CatalogGroup)`
then raises `TypeError` (Context item 3).

### D2: No new guard

The equivalence of D1 rests on Context item 2. The tests of `tests/test_models_manifest.py` already check it for
each union of the pinned manifest, and they run in `hatch run release`. A new post-processor guard would check the
same facts again.

### D3: The performance target is a pass or fail check

Task 3.2 measures the documents of Context item 4 with `scripts/bench_serialization.py` before and after the change.
The check passes when the targets of Goals 1 and 2 hold. If it fails, the implementation stops, and the design is
revisited before a pull request. The pull request reports both runs.

## Risks / Trade-offs

1. [A later manifest adds a variant that accepts the property of another variant] → `left_to_right` then picks the
   first variant that validates, and smart mode could pick another one. The tests of D2 fail first.
2. [A later pydantic changes the cost of smart mode or of `left_to_right`] → The benchmark of each pull request shows
   the change.
3. [The gain is small for documents other than catalogs] → Goal 2 requires only that they are not slower.

## Migration Plan

1. Run `hatch run generate`, and commit the regenerated `models.py` with the post-processor change.
2. Rollback: revert the commit.
