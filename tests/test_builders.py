"""Tests for back-matter resource builder helpers."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from oscal_bindings import make_hash, make_resource, make_rlink
from oscal_bindings.models import Algorithm, Hash, Resource, Rlink

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
DIGEST = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestMakeHash:
    def test_default_algorithm_is_sha256(self):
        h = make_hash(DIGEST)
        assert isinstance(h, Hash)
        assert h.algorithm == Algorithm.SHA_256
        assert h.value == DIGEST

    def test_algorithm_by_enum(self):
        h = make_hash(DIGEST, algorithm=Algorithm.SHA_512)
        assert h.algorithm == Algorithm.SHA_512

    def test_algorithm_by_string(self):
        h = make_hash(DIGEST, algorithm="SHA-384")
        assert h.algorithm == Algorithm.SHA_384

    def test_invalid_algorithm_string_raises(self):
        with pytest.raises(ValueError, match="'MD5' is not a valid Algorithm"):
            make_hash(DIGEST, algorithm="MD5")


class TestMakeRlink:
    def test_minimal(self):
        link = make_rlink("https://example.com/a.pdf")
        assert isinstance(link, Rlink)
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


class TestMakeResource:
    def test_minimal_generates_uuid4(self):
        r = make_resource()
        assert isinstance(r, Resource)
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
        with pytest.raises(ValidationError):
            make_resource(title="line one\nline two")

    def test_no_document_ids_by_default(self):
        # Backward-compat guard: the additive document_ids param defaults to
        # None, so an existing caller's resource has document_ids is None.
        r = make_resource()
        assert r.document_ids is None


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
        assert resource.rlinks[1].hashes[0].algorithm == Algorithm.SHA_256
