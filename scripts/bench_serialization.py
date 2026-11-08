"""Benchmark parse and serialize time for one OSCAL document.

Reports the median of N timed runs (after one untimed warm-up), with cyclic GC
enabled and with cyclic GC disabled, for:

- ``parse_oscal(bytes)``
- ``serialize_oscal(doc, indent=None)`` (compact)
- ``serialize_oscal(doc)`` (indent=2)
- ``doc.model_dump_json()`` (argument-less default path)
- ``pydantic_core.to_json(doc)`` (framework path, e.g. MCP text content)

Uses only API that exists both before and after the default-serialization fix
(GitHub issue #5), so the same script measures both trees. Output sizes are
printed alongside times so a change in what the default paths emit is visible.

The GC-off median measures the binding alone. The GC-on median also includes the
cyclic GC cost, which grows with the objects the process holds (design D8 of the
discriminate-document-union change). So the script times the parse case before
it parses the document for the serialize cases, and it drops the result of each
run after its time is read: the next run holds no previous result, and no time
includes the deallocation of a result.

Usage::

    hatch run python scripts/bench_serialization.py [--catalog PATH] [--runs N]
"""

from __future__ import annotations

import argparse
import gc
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pydantic
import pydantic_core

from oscal_bindings import parse_oscal, serialize_oscal

if TYPE_CHECKING:
    from collections.abc import Callable

# The SP 800-53 rev5 catalog from the pinned NIST corpus cache (populated by the
# test suite; see tests/support/corpus.py).
DEFAULT_CATALOG = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / ".corpus_cache"
    / "oscal-content-78650f02ad9321bb7b817846f8fbd4f2bcd620de"
    / "nist.gov"
    / "SP800-53"
    / "rev5"
    / "json"
    / "NIST_SP-800-53_rev5_catalog.json"
)
DEFAULT_RUNS = 7


def _median_ms(fn: Callable[[], object], runs: int, *, collect: bool) -> float:
    """Run ``fn`` once untimed, then ``runs`` times; return the median ms.

    ``collect`` False disables cyclic GC for each timed call. The result of
    each call is dropped after its time is read.
    """
    fn()  # warm-up
    samples: list[float] = []
    enabled = gc.isenabled()
    for _ in range(runs):
        gc.collect()
        if not collect:
            gc.disable()
        try:
            start = time.perf_counter()
            result = fn()
            samples.append((time.perf_counter() - start) * 1000.0)
        finally:
            if enabled:
                gc.enable()
        del result
    return statistics.median(samples)


def _size(value: object) -> str:
    return f"{len(value):,} B" if isinstance(value, str | bytes) else "-"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    args = parser.parse_args(argv)

    if args.runs < 1:
        print("--runs must be >= 1", file=sys.stderr)
        return 2
    if not args.catalog.is_file():
        print(
            f"Catalog not found: {args.catalog}\n"
            "Populate the corpus cache by running the test suite, or pass --catalog.",
            file=sys.stderr,
        )
        return 2

    raw = args.catalog.read_bytes()

    print(f"Document: {args.catalog.name} ({len(raw):,} B)")
    print(
        f"Python {platform.python_version()}, pydantic {pydantic.VERSION}, "
        f"pydantic-core {pydantic_core.__version__}"
    )
    print(f"Median of {args.runs} runs after 1 warm-up\n")
    width = len("serialize_oscal(doc, indent=None)")
    print(
        f"| {'Path':<{width}} | {'GC on ms':>9} | {'GC off ms':>9} | {'Output':>14} |"
    )
    print(f"|{'-' * (width + 2)}|{'-' * 11}|{'-' * 11}|{'-' * 16}|")

    def row(name: str, fn: Callable[[], object]) -> None:
        on = _median_ms(fn, args.runs, collect=True)
        off = _median_ms(fn, args.runs, collect=False)
        size = _size(fn())
        print(f"| {name:<{width}} | {on:>9.1f} | {off:>9.1f} | {size:>14} |")

    # The parse case runs first, so no parsed document is live while it runs.
    row("parse_oscal(bytes)", lambda: parse_oscal(raw))
    doc = parse_oscal(raw)
    for name, fn in [
        (
            "serialize_oscal(doc, indent=None)",
            lambda: serialize_oscal(doc, indent=None),
        ),
        ("serialize_oscal(doc)", lambda: serialize_oscal(doc)),
        ("doc.model_dump_json()", doc.model_dump_json),
        ("pydantic_core.to_json(doc)", lambda: pydantic_core.to_json(doc)),
    ]:
        row(name, fn)
    return 0


if __name__ == "__main__":
    sys.exit(main())
