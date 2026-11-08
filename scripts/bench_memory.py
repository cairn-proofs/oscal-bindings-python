"""Measure the peak traced memory of a parse, with ``tracemalloc``.

Reports, for the JSON and the YAML path:

- the SP 800-53 rev5 catalog (valid input), as a multiple of its input size
- a flow mapping of 150,000 unknown short keys (invalid input, many error entries)

The peak is the traced memory above the level before the call, in MB, and the
factor divides it by the input size. YAML needs the ``yaml`` extra.

Usage::

    hatch run python scripts/bench_memory.py [--catalog-dir PATH]

``--catalog-dir`` is the ``nist.gov/SP800-53/rev5`` directory of the corpus cache,
with a ``json`` and a ``yaml`` folder.
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import json
import platform
import sys
import tracemalloc
from pathlib import Path
from typing import TYPE_CHECKING

import pydantic
import pydantic_core

from oscal_bindings import OscalParseError, parse_oscal, parse_oscal_yaml

if TYPE_CHECKING:
    from collections.abc import Callable

DEFAULT_DIR = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / ".corpus_cache"
    / "oscal-content-78650f02ad9321bb7b817846f8fbd4f2bcd620de"
    / "nist.gov"
    / "SP800-53"
    / "rev5"
)
CATALOG = "NIST_SP-800-53_rev5_catalog"
KEY_COUNT = 150_000


def peak_mb(fn: Callable[[bytes], object], data: bytes) -> float:
    """Peak traced memory of ``fn(data)`` above the starting level, in MB.

    An ``OscalParseError`` counts: the peak is reached before it is raised.
    """
    gc.collect()
    tracemalloc.start()
    try:
        base = tracemalloc.get_traced_memory()[0]
        with contextlib.suppress(OscalParseError):
            fn(data)
        return (tracemalloc.get_traced_memory()[1] - base) / 1e6
    finally:
        tracemalloc.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalog-dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args(argv)

    json_path = args.catalog_dir / "json" / f"{CATALOG}.json"
    yaml_path = args.catalog_dir / "yaml" / f"{CATALOG}.yaml"
    for path in (json_path, yaml_path):
        if not path.is_file():
            print(
                f"Not found: {path}\n"
                "Populate the corpus cache by running the test suite, or pass "
                "--catalog-dir.",
                file=sys.stderr,
            )
            return 2

    keys = ", ".join(f"k{i}: 1" for i in range(KEY_COUNT))
    cases: list[tuple[str, Callable[[bytes], object], bytes]] = [
        ("catalog, JSON", parse_oscal, json_path.read_bytes()),
        ("catalog, YAML", parse_oscal_yaml, yaml_path.read_bytes()),
        (
            "150,000-key mapping, JSON",
            parse_oscal,
            json.dumps({"catalog": {f"k{i}": 1 for i in range(KEY_COUNT)}}).encode(),
        ),
        (
            "150,000-key mapping, YAML",
            parse_oscal_yaml,
            f"catalog: {{{keys}}}".encode(),
        ),
    ]

    print(
        f"Python {platform.python_version()}, pydantic {pydantic.VERSION}, "
        f"pydantic-core {pydantic_core.__version__}\n"
    )
    width = max(len(name) for name, _, _ in cases)
    print(f"| {'Input':<{width}} | {'Input MB':>8} | {'Peak MB':>8} | {'Factor':>6} |")
    print(f"|{'-' * (width + 2)}|{'-' * 10}|{'-' * 10}|{'-' * 8}|")
    for name, fn, data in cases:
        peak = peak_mb(fn, data)
        size = len(data) / 1e6
        factor = peak / size
        print(f"| {name:<{width}} | {size:>8.2f} | {peak:>8.1f} | {factor:>5.1f}x |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
