"""Tests for back-matter resource builder helpers."""

from __future__ import annotations

import re

import pytest

from oscal_bindings import (
    OscalBuilderError,
    OscalParseError,
    make_hash,
    make_resource,
    make_rlink,
)
from oscal_bindings.models import (
    BackMatterResource,
    BackMatterResourceRlink,
    DocumentId,
    Hash,
    HashAlgorithm,
)

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestMakeHash:
    def test_default_algorithm_is_sha256(self):
        h = make_hash(DIGEST)
        assert isinstance(h, Hash)
        assert h.algorithm == HashAlgorithm.SHA_256
        assert h.value == DIGEST

    def test_algorithm_by_enum(self):
        h = make_hash(DIGEST, algorithm=HashAlgorithm.SHA_512)
        assert h.algorithm == HashAlgorithm.SHA_512

    def test_algorithm_by_string(self):
        h = make_hash(DIGEST, algorithm="SHA-384")
        assert h.algorithm == HashAlgorithm.SHA_384

    def test_algorithm_string_equals_enum(self):
        by_string = make_hash(DIGEST, algorithm="SHA-256")
        by_enum = make_hash(DIGEST, algorithm=HashAlgorithm.SHA_256)
        assert by_string == by_enum
        assert by_string.algorithm is HashAlgorithm.SHA_256

    @pytest.mark.parametrize("algorithm", ["MD5", "SHA-999"])
    def test_algorithm_that_is_not_named_is_kept_as_given(self, algorithm):
        assert make_hash(DIGEST, algorithm=algorithm).algorithm == algorithm

    def test_invalid_algorithm_raises_builder_error(self):
        with pytest.raises(OscalBuilderError) as info:
            make_hash(DIGEST, algorithm=" SHA-256")
        assert info.value.errors
        assert isinstance(info.value, ValueError)
        assert not isinstance(info.value, OscalParseError)


class TestMakeRlink:
    def test_minimal(self):
        link = make_rlink("https://example.com/a.pdf")
        assert isinstance(link, BackMatterResourceRlink)
        assert link.href == "https://example.com/a.pdf"
        assert link.media_type is None
        assert link.hashes is None

    def test_with_media_type(self):
        link = make_rlink("https://example.com/a.pdf", media_type="application/pdf")
        assert link.media_type == "application/pdf"

    def test_with_hashes(self):
        h = make_hash(DIGEST)
        link = make_rlink("https://example.com/a.pdf", hashes=[h])
        assert link.hashes == [h]

    def test_unvalidated_hash_item_raises(self):
        bad = Hash.model_construct(algorithm=" SHA-256", value="ab")
        with pytest.raises(OscalBuilderError):
            make_rlink("https://example.com/a.pdf", hashes=[bad])


class TestMakeResource:
    def test_minimal_generates_uuid4(self):
        r = make_resource()
        assert isinstance(r, BackMatterResource)
        assert UUID_RE.match(r.uuid)

    def test_distinct_uuids_per_call(self):
        a = make_resource()
        b = make_resource()
        assert a.uuid != b.uuid

    def test_caller_supplied_uuid_preserved(self):
        u = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        r = make_resource(uuid=u)
        assert r.uuid == u

    def test_with_title_and_description(self):
        r = make_resource(title="T", description="D")
        assert r.title == "T"
        assert r.description == "D"

    def test_invalid_title_raises(self):
        # Resource.title is constrained to one-line strings (^[^\n]+$).
        with pytest.raises(OscalBuilderError):
            make_resource(title="line one\nline two")

    def test_no_document_ids_by_default(self):
        # Backward-compat guard: the additive document_ids param defaults to
        # None, so an existing caller's resource has document_ids is None.
        r = make_resource()
        assert r.document_ids is None

    # document_ids is validated at construction like rlinks (Property 4;
    # Requirements 1.7, 2.13, 3.8). Pre-fix it was assigned post-construction
    # with validate_assignment off, so these inputs were stored unchecked.

    def test_empty_document_ids_raises(self):
        # Resource.document_ids has min_length=1 ("document-ids": [] is
        # invalid OSCAL).
        with pytest.raises(OscalBuilderError):
            make_resource(document_ids=[])

    def test_non_document_id_items_raise(self):
        with pytest.raises(OscalBuilderError):
            make_resource(document_ids=["x"])  # type: ignore[list-item]

    def test_mixed_document_id_items_raise(self):
        with pytest.raises(OscalBuilderError):
            make_resource(
                document_ids=[DocumentId(identifier="x"), "y"]  # type: ignore[list-item]
            )

    def test_valid_document_ids_equal_alias_dict_construction(self):
        u = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        ids = [
            DocumentId(identifier="doc-1"),
            DocumentId(scheme="https://example.com/ids", identifier="doc-2"),
        ]
        r = make_resource(uuid=u, title="T", document_ids=ids)
        # The pre-fix way: alias-keyed dict through model_validate.
        expected = BackMatterResource.model_validate(
            {
                "uuid": u,
                "title": "T",
                "document-ids": [
                    d.model_dump(by_alias=True, exclude_none=True) for d in ids
                ],
            }
        )
        assert r == expected
        assert r.document_ids == ids


class TestMakeResourceKey:
    def test_same_key_gives_same_uuid(self):
        a = make_resource(key="https://example.org/a", title="One")
        b = make_resource(key="https://example.org/a", title="Two")
        assert a.uuid == b.uuid

    def test_key_gives_uuid_version_5(self):
        r = make_resource(key="https://example.org/policies/données")
        assert r.uuid == "daa01937-2576-5dc8-9fb0-4da240946a5e"

    def test_key_with_uuid_raises(self):
        with pytest.raises(OscalBuilderError) as info:
            make_resource(key="k", uuid="f47ac10b-58cc-4372-a567-0e02b2c3d479")
        assert [(e["type"], e["loc"]) for e in info.value.errors] == [
            ("key_with_uuid", ("key",))
        ]

    def test_empty_key_raises(self):
        with pytest.raises(OscalBuilderError) as info:
            make_resource(key="")
        assert [(e["type"], e["loc"]) for e in info.value.errors] == [
            ("empty_key", ("key",))
        ]

    def test_no_key_and_no_uuid_gives_uuid_version_4(self):
        assert UUID_RE.match(make_resource().uuid)

    @pytest.mark.parametrize("key", [5, b"abc"])
    def test_key_that_is_not_a_string_raises(self, key):
        with pytest.raises(OscalBuilderError) as info:
            make_resource(key=key)  # type: ignore[arg-type]
        assert [(e["type"], e["loc"]) for e in info.value.errors] == [
            ("string_type", ("key",))
        ]


class TestBuilderErrorIsNotParseError:
    def test_resource_error_is_value_error_not_parse_error(self):
        with pytest.raises(OscalBuilderError) as info:
            make_resource(title="line one\nline two")
        assert isinstance(info.value, ValueError)
        assert not isinstance(info.value, OscalParseError)

    def test_unvalidated_document_id_item_raises(self):
        bad = DocumentId.model_construct()
        with pytest.raises(OscalBuilderError):
            make_resource(document_ids=[bad])


class TestComposability:
    def test_full_composition(self):
        resource = make_resource(
            title="Evidence",
            description="Two mirrors of the same file",
            rlinks=[
                make_rlink(
                    "https://example.com/a.pdf",
                    media_type="application/pdf",
                    hashes=[make_hash(DIGEST)],
                ),
                make_rlink("s3://bucket/a.pdf", hashes=[make_hash(DIGEST)]),
            ],
        )
        assert resource.title == "Evidence"
        assert len(resource.rlinks) == 2
        assert resource.rlinks[0].media_type == "application/pdf"
        assert resource.rlinks[0].hashes[0].value == DIGEST
        assert resource.rlinks[1].hashes[0].algorithm == HashAlgorithm.SHA_256
