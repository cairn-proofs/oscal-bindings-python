"""Benchmark parse and serialize time for one OSCAL document.

Reports the median of N timed runs (after one untimed warm-up) for:

- ``parse_oscal(bytes)``
- ``serialize_oscal(doc, indent=None)`` (compact)
- ``serialize_oscal(doc)`` (indent=2)
- ``doc.model_dump_json()`` (argument-less default path)
- ``pydantic_core.to_json(doc)`` (framework path, e.g. MCP text content)

Uses only API that exists both before and after the default-serialization fix
(GitHub issue #5), so the same script measures both trees. Output sizes are
printed alongside times so a change in what the default paths emit is visible.

Usage::

    hatch run python scripts/bench_serialization.py [--catalog PATH] [--runs N]
"""

from __future__ import annotations

import argparse
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


def _median_ms(fn: Callable[[], object], runs: int) -> tuple[float, object]:
    """Run ``fn`` once untimed, then ``runs`` times; return (median ms, result)."""
    result = fn()  # warm-up
    samples: list[float] = []
    for _ in range(runs):
        start = time.perf_counter()
        result = fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return statistics.median(samples), result


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
    doc = parse_oscal(raw)

    cases: list[tuple[str, Callable[[], object]]] = [
        ("parse_oscal(bytes)", lambda: parse_oscal(raw)),
        (
            "serialize_oscal(doc, indent=None)",
            lambda: serialize_oscal(doc, indent=None),
        ),
        ("serialize_oscal(doc)", lambda: serialize_oscal(doc)),
        ("doc.model_dump_json()", doc.model_dump_json),
        ("pydantic_core.to_json(doc)", lambda: pydantic_core.to_json(doc)),
    ]

    print(f"Document: {args.catalog.name} ({len(raw):,} B)")
    print(
        f"Python {platform.python_version()}, pydantic {pydantic.VERSION}, "
        f"pydantic-core {pydantic_core.__version__}"
    )
    print(f"Median of {args.runs} runs after 1 warm-up\n")
    width = max(len(name) for name, _ in cases)
    print(f"| {'Path':<{width}} | {'Median ms':>10} | {'Output':>14} |")
    print(f"|{'-' * (width + 2)}|{'-' * 12}|{'-' * 16}|")
    for name, fn in cases:
        ms, result = _median_ms(fn, args.runs)
        print(f"| {name:<{width}} | {ms:>10.1f} | {_size(result):>14} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
