"""Test-support package for the property-based test suite.

Modules here are importable helpers (not collected as tests). ``version_package``
holds the pre-move public-surface snapshot and schema ``$id`` helpers shared by the
``v1`` back-compatibility tests. ``corpus`` holds the Corpus_Fetcher: pinning,
fetch, cache, concurrency, and hard-fail logic for the remote OSCAL corpora that
seed the corpus-driven property tests.
"""
