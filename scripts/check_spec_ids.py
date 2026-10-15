"""Check the requirement and scenario identifiers of the main OpenSpec specs.

The main specs are the files ``openspec/specs/<capability>/spec.md``. The ledger
``openspec/spec-ids.yaml`` holds one prefix for each capability and each retired
identifier. The rules are the spec-identifier rules in ``openspec/config.yaml``.
Nothing here is specific to one project. Each failure starts with the name of
the rule that failed:

1. ``requirement-id``: each requirement heading has a well-formed identifier,
   such as ``### Requirement: ABC-001 Title``.
2. ``scenario-id``: each scenario heading has a well-formed identifier, such as
   ``#### Scenario: ABC-001.01 Title``.
3. ``scenario-parent``: each scenario identifier extends the identifier of the
   requirement above it.
4. ``ledger``: the ledger exists and is well-formed.
5. ``prefix``: each capability has exactly one prefix, and its headings use it.
6. ``duplicate-id``: each identifier is on one heading only.
7. ``next``: each requirement number is below ``next`` of its prefix.
8. ``missing-id``: each requirement number below ``next`` is live or retired.
9. ``vanished-scenario``: each scenario identifier at the base ref is live or
   retired. A retired requirement retires each of its scenarios.
10. ``retired-reuse``: no heading uses a retired identifier.
11. ``replaced-by``: each ``replaced_by`` names a live identifier.
12. ``citation``: each citation ``[ABC-001]`` or ``[ABC-001.01]`` with a ledger
    prefix is live or retired. Other bracketed tokens, such as NIST control
    ``[AC-2]``, are not citations.
13. ``link``: each link to a heading of a main spec names a heading that exists.

Only main specs are checked. Change specs under ``openspec/changes/`` are not.
Exits 1 when any check fails. ``SPEC_IDS_BASE`` names the git ref whose scenario
identifiers must not vanish (default ``HEAD``). Run it from the repository root.
It needs PyYAML, which no Hatch env in this repo declares.
"""

from __future__ import annotations

import os
import posixpath
import re
import shutil
import subprocess  # nosec B404
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

Files = dict[str, str]
"""Repository-relative POSIX path -> file text."""

LEDGER = "openspec/spec-ids.yaml"
SPEC_PATH = re.compile(r"^openspec/specs/([^/]+)/spec\.md$")
REQUIREMENT = re.compile(r"^### Requirement:\s*(.*)$")
SCENARIO = re.compile(r"^#### Scenario:\s*(.*)$")
LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
REQUIREMENT_ID = re.compile(r"^([A-Z]{2,5})-(\d+) \S")
SCENARIO_ID = re.compile(r"^([A-Z]{2,5})-(\d+)\.(\d+) \S")
ID = re.compile(r"^([A-Z]{2,5})-(\d+)(?:\.(\d+))?$")
CITATION = re.compile(r"\[([A-Z]{2,5}-\d+(?:\.\d+)?)\]")
PREFIX = re.compile(r"^[A-Z]{2,5}$")
FENCE = re.compile(r"^\s*(```|~~~)")
CODE_SPAN = re.compile(r"`[^`]*`")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
REQUIREMENT_WIDTH = 3
SCENARIO_WIDTH = 2


# --- Markdown -----------------------------------------------------------------


def prose_lines(text: str) -> list[tuple[int, str]]:
    """Return the lines outside fenced code blocks, with 1-based line numbers."""
    out: list[tuple[int, str]] = []
    fenced = False
    for index, line in enumerate(text.split("\n")):
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            out.append((index + 1, line))
    return out


def without_code(line: str) -> str:
    """Remove inline code spans from a line."""
    return CODE_SPAN.sub("", line)


class Slugger:
    """GitHub heading anchors, as the ``github-slugger`` package makes them.

    The slug is the lowercase text without punctuation, with each space replaced
    by ``-``. A repeated slug gets the suffix ``-1``, ``-2`` and so on.
    """

    _STRIP = re.compile(r"[^\w\- ]")

    def __init__(self) -> None:
        self._occurrences: dict[str, int] = {}

    @classmethod
    def plain(cls, value: str) -> str:
        """Return the slug of ``value`` without the duplicate suffix."""
        return cls._STRIP.sub("", value.lower()).replace(" ", "-")

    def slug(self, value: str) -> str:
        """Return the unique slug of ``value`` in this document."""
        original = result = self.plain(value)
        while result in self._occurrences:
            self._occurrences[original] += 1
            result = f"{original}-{self._occurrences[original]}"
        self._occurrences[result] = 0
        return result


def anchors(text: str) -> set[str]:
    """Return the GitHub anchor of each heading in a Markdown file."""
    slugger = Slugger()
    out: set[str] = set()
    for _, line in prose_lines(text):
        match = HEADING.match(line)
        if match:
            out.add(slugger.slug(match.group(1).replace("`", "")))
    return out


def read_repository(root: Path, extra: tuple[str, ...] = ()) -> Files:
    """Read each Markdown file under ``openspec/`` and ``docs/``, and each ``extra``."""
    files: Files = {}
    for directory in ("openspec", "docs"):
        base = root / directory
        if base.is_dir():
            for path in sorted(base.rglob("*.md")):
                if path.is_file():
                    files[path.relative_to(root).as_posix()] = path.read_text("utf-8")
    for rel in extra:
        path = root / rel
        if path.is_file():
            files[rel] = path.read_text("utf-8")
    return files


# --- Identifiers ----------------------------------------------------------------


def canonical(identifier: str) -> str | None:
    """Return the canonical key of an identifier: ``ABC-002`` and ``ABC-2`` are one."""
    match = ID.match(identifier)
    if not match:
        return None
    prefix, number, sub = match.groups()
    key = f"{prefix}-{int(number)}"
    return key if sub is None else f"{key}.{int(sub)}"


def render(key: str) -> str:
    """Render a canonical key in the published form, such as ``ABC-002.01``."""
    match = ID.match(key)
    if not match:
        return key
    prefix, number, sub = match.groups()
    requirement = f"{prefix}-{number.zfill(REQUIREMENT_WIDTH)}"
    return requirement if sub is None else f"{requirement}.{sub.zfill(SCENARIO_WIDTH)}"


def _well_formed(digits: str, width: int) -> bool:
    """Return True when ``digits`` has no surplus zero and at least ``width`` digits."""
    return digits == str(int(digits)).zfill(width)


@dataclass
class Heading:
    """A requirement or scenario heading of a main spec."""

    file: str
    text: str
    kind: Literal["requirement", "scenario"]
    id: str | None = None
    """Canonical key, such as ``ABC-2`` or ``ABC-2.1``. None when malformed."""
    prefix: str | None = None


def parse_spec(file: str, text: str) -> tuple[list[Heading], list[str]]:
    """Return the headings of one spec and its heading-form failures."""
    headings: list[Heading] = []
    bad: list[str] = []
    current: Heading | None = None
    for _, line in prose_lines(text):
        req = REQUIREMENT.match(line)
        if req:
            title = req.group(1)
            m = REQUIREMENT_ID.match(title)
            ok = m is not None and _well_formed(m.group(2), REQUIREMENT_WIDTH)
            current = Heading(file, title, "requirement")
            if m and ok:
                current.id = f"{m.group(1)}-{int(m.group(2))}"
                current.prefix = m.group(1)
            else:
                bad.append(
                    f'[requirement-id] {file}: requirement heading "{title}" has no '
                    "well-formed identifier."
                )
            headings.append(current)
            continue
        sc = SCENARIO.match(line)
        if not sc:
            continue
        title = sc.group(1)
        m = SCENARIO_ID.match(title)
        ok = (
            m is not None
            and _well_formed(m.group(2), REQUIREMENT_WIDTH)
            and _well_formed(m.group(3), SCENARIO_WIDTH)
        )
        heading = Heading(file, title, "scenario")
        headings.append(heading)
        if not (m and ok):
            bad.append(
                f'[scenario-id] {file}: scenario heading "{title}" has no '
                "well-formed identifier."
            )
            continue
        heading.id = f"{m.group(1)}-{int(m.group(2))}.{int(m.group(3))}"
        heading.prefix = m.group(1)
        parent = f"{m.group(1)}-{int(m.group(2))}"
        if current is None or current.id != parent:
            owner = (
                render(current.id)
                if current and current.id
                else "no identified requirement"
            )
            bad.append(
                f'[scenario-parent] {file}: scenario heading "{title}" '
                f"is under {owner}."
            )
    return headings, bad


# --- Ledger ---------------------------------------------------------------------


@dataclass
class Ledger:
    """The parsed ``openspec/spec-ids.yaml``."""

    prefixes: dict[str, tuple[str, int]] = field(default_factory=dict)
    """Prefix -> (capability, next)."""
    retired: dict[str, str | None] = field(default_factory=dict)
    """Canonical key -> canonical ``replaced_by`` key, or None."""

    def is_retired(self, key: str) -> bool:
        """Return True when ``key`` or its requirement is retired."""
        return key in self.retired or key.split(".", maxsplit=1)[0] in self.retired


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def parse_ledger(text: str | None, failures: list[str]) -> Ledger | None:
    """Parse the ledger and append each ledger failure to ``failures``."""
    if text is None:
        failures.append(f"[ledger] {LEDGER} does not exist.")
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        failures.append(f"[ledger] {LEDGER} is not valid YAML: {error}")
        return None
    ledger = Ledger()
    prefixes = data.get("prefixes") if isinstance(data, dict) else None
    if not isinstance(prefixes, dict):
        failures.append(f"[ledger] {LEDGER} has no prefixes map.")
        return ledger
    for prefix, entry in prefixes.items():
        capability = entry.get("capability") if isinstance(entry, dict) else None
        nxt = entry.get("next") if isinstance(entry, dict) else None
        if (
            not isinstance(prefix, str)
            or not PREFIX.match(prefix)
            or not isinstance(capability, str)
            or not _positive_int(nxt)
        ):
            failures.append(
                f'[ledger] {LEDGER}: prefix entry "{prefix}" needs a capability '
                "and a positive integer next."
            )
            continue
        ledger.prefixes[prefix] = (capability, nxt)
    retired = data.get("retired")
    if not isinstance(retired, list):
        failures.append(f"[ledger] {LEDGER} has no retired list.")
        return ledger
    for entry in retired:
        raw_id = entry.get("id") if isinstance(entry, dict) else None
        key = canonical(raw_id) if isinstance(raw_id, str) else None
        reason = entry.get("reason") if isinstance(entry, dict) else None
        if key is None or not isinstance(reason, str) or not reason.strip():
            failures.append(
                f"[ledger] {LEDGER}: retired entry {entry!r} needs a well-formed id "
                "and a reason."
            )
            continue
        target = entry.get("replaced_by")
        target_key = canonical(target) if isinstance(target, str) else None
        if target is not None and target_key is None:
            failures.append(
                f"[ledger] {LEDGER}: replaced_by of {raw_id} is not a well-formed "
                "identifier."
            )
            continue
        ledger.retired[key] = target_key
    return ledger


# --- Checks ---------------------------------------------------------------------


def _check_prefixes(
    ledger: Ledger,
    specs: list[str],
    identified: list[Heading],
    failures: list[str],
) -> None:
    """prefix: one prefix per capability, and headings use it."""
    prefix_of: dict[str, list[str]] = {}
    for prefix, (capability, _) in ledger.prefixes.items():
        prefix_of.setdefault(capability, []).append(prefix)
    for capability, prefixes in prefix_of.items():
        if len(prefixes) > 1:
            failures.append(
                f"[prefix] capability {capability} has {len(prefixes)} prefixes: "
                f"{', '.join(prefixes)}."
            )
    for file in specs:
        capability = file.split("/")[2]  # openspec/specs/<capability>/spec.md
        prefixes = prefix_of.get(capability, [])
        if not prefixes:
            failures.append(
                f"[prefix] capability {capability} has no prefix in {LEDGER}."
            )
            continue
        failures.extend(
            f'[prefix] {file}: heading "{heading.text}" uses '
            f"{heading.prefix}, not the prefix {prefixes[0]} of {capability}."
            for heading in identified
            if heading.file == file and heading.prefix not in prefixes
        )


def _check_numbers(
    ledger: Ledger,
    identified: list[Heading],
    live: dict[str, list[Heading]],
    failures: list[str],
) -> None:
    """next and missing-id: numbers are allocated forward and never vanish."""
    for heading in identified:
        if heading.kind != "requirement" or heading.id is None:
            continue
        entry = ledger.prefixes.get(heading.prefix or "")
        number = int(heading.id.split("-")[1])
        if entry and number >= entry[1]:
            failures.append(
                f'[next] {heading.file}: heading "{heading.text}" is at or above '
                f"next ({entry[1]}) for {heading.prefix}."
            )
    for prefix, (_, nxt) in ledger.prefixes.items():
        for number in range(1, nxt):
            key = f"{prefix}-{number}"
            if key not in live and key not in ledger.retired:
                failures.append(
                    f"[missing-id] {render(key)} is neither live nor retired."
                )


def _check_base(
    ledger: Ledger,
    base: Files | Exception,
    live: dict[str, list[Heading]],
    failures: list[str],
) -> None:
    """vanished-scenario: scenario identifiers at the base ref never vanish."""
    if isinstance(base, Exception):
        failures.append(
            f"[vanished-scenario] cannot read the main specs at the base ref: {base}"
        )
        return
    before: set[str] = set()
    for file, text in base.items():
        if not SPEC_PATH.match(file):
            continue
        for heading in parse_spec(file, text)[0]:
            if heading.kind == "scenario" and heading.id:
                before.add(heading.id)
    failures.extend(
        f"[vanished-scenario] {render(key)} is in the base specs and is "
        "neither live nor retired."
        for key in sorted(before)
        if key not in live and not ledger.is_retired(key)
    )


def _check_retired(
    ledger: Ledger, live: dict[str, list[Heading]], failures: list[str]
) -> None:
    """retired-reuse and replaced-by: retired stays retired, relocations resolve."""
    for key, replaced_by in ledger.retired.items():
        failures.extend(
            f'[retired-reuse] {heading.file}: heading "{heading.text}" uses the '
            f"retired identifier {render(key)}."
            for heading in live.get(key, [])
        )
        if replaced_by is not None and replaced_by not in live:
            failures.append(
                f"[replaced-by] retired {render(key)} has replaced_by "
                f"{render(replaced_by)}, which is not live."
            )


def _check_references(
    files: Files,
    ledger: Ledger | None,
    live: dict[str, list[Heading]],
    failures: list[str],
) -> None:
    """citation and link: citations and spec links in specs and docs resolve."""
    sources = sorted(
        f
        for f in files
        if f.endswith(".md") and f.startswith(("openspec/specs/", "docs/"))
    )
    anchor_cache: dict[str, set[str]] = {}
    for file in sources:
        for line_no, raw in prose_lines(files[file]):
            line = without_code(raw)
            for cited in CITATION.findall(line):
                key = canonical(cited)
                # Only ledger prefixes make a citation. [AC-2] is a NIST control.
                if key is None or ledger is None:
                    continue
                if key.split("-")[0] not in ledger.prefixes:
                    continue
                if key not in live and not ledger.is_retired(key):
                    failures.append(
                        f"[citation] {file}:{line_no}: citation [{cited}] is neither "
                        "live nor retired."
                    )
            for target in LINK.findall(line):
                if re.match(r"^[a-z]+:", target, re.IGNORECASE):
                    continue
                if target.startswith("#") or "#" not in target:
                    continue
                href, anchor = target.split("#", 1)
                resolved = posixpath.normpath(
                    posixpath.join(posixpath.dirname(file), href)
                )
                if not SPEC_PATH.match(resolved):
                    continue
                if resolved not in anchor_cache:
                    text = files.get(resolved)
                    anchor_cache[resolved] = set() if text is None else anchors(text)
                if anchor not in anchor_cache[resolved]:
                    failures.append(
                        f"[link] {file}:{line_no}: link {target} names no heading "
                        f"in {resolved}."
                    )


def check_spec_ids(files: Files, base: Files | Exception) -> list[str]:
    """Run every check. ``files`` holds openspec/ and docs/, ``base`` the base specs."""
    failures: list[str] = []
    # Main specs only. Change specs are out of scope.
    specs = sorted(f for f in files if SPEC_PATH.match(f))
    headings: list[Heading] = []
    for file in specs:
        parsed, bad = parse_spec(file, files[file])
        headings.extend(parsed)
        failures.extend(bad)
    identified = [h for h in headings if h.id is not None]
    live: dict[str, list[Heading]] = {}
    for heading in identified:
        live.setdefault(heading.id or "", []).append(heading)

    # duplicate-id: one heading per identifier.
    for key, owners in live.items():
        if len(owners) > 1:
            where = ", ".join(f'{h.file} "{h.text}"' for h in owners)
            failures.append(
                f"[duplicate-id] {render(key)} is on {len(owners)} headings: {where}."
            )

    ledger = parse_ledger(files.get(LEDGER), failures)
    if ledger is not None:
        _check_prefixes(ledger, specs, identified, failures)
        _check_numbers(ledger, identified, live, failures)
        _check_base(ledger, base, live, failures)
        _check_retired(ledger, live, failures)
    _check_references(files, ledger, live, failures)
    return failures


# --- CLI ------------------------------------------------------------------------


def read_base(root: Path, ref: str) -> Files | Exception:
    """Return the main specs at a git ref, or the error that stopped the read."""
    # Runs git with fixed arguments and no shell (the nosec markers below).
    git = shutil.which("git")
    if git is None:
        return RuntimeError("git is not on PATH")

    def run(*args: str) -> str:
        return subprocess.run(  # noqa: S603  # nosec B603
            [git, *args], cwd=root, capture_output=True, text=True, check=True
        ).stdout

    try:
        files: Files = {}
        listing = run("ls-tree", "-r", "--name-only", ref, "--", "openspec/specs")
        for file in listing.splitlines():
            if SPEC_PATH.match(file):
                files[file] = run("show", f"{ref}:{file}")
    except subprocess.CalledProcessError as error:
        first = (error.stderr or "").strip().splitlines()
        return RuntimeError(f"{ref}: {first[0] if first else error}")
    return files


def main() -> int:
    """Check the repository in the current directory."""
    root = Path.cwd()
    ref = os.environ.get("SPEC_IDS_BASE") or "HEAD"
    failures = check_spec_ids(read_repository(root, (LEDGER,)), read_base(root, ref))
    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(f"\n{len(failures)} spec identifier failure(s)")
        return 1
    print("spec identifiers: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
