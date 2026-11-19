"""Hand-written docstrings use Markdown code spans, not Sphinx roles.

pdoc keeps the ``~`` prefix and the private module path of a Sphinx role, so a
reader sees text such as ``~oscal_bindings.v1.models.CatalogDocument``. A code
span of the exported name shows correctly, and pdoc links it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src" / "oscal_bindings"
GENERATED = SRC_DIR / "v1" / "models.py"
SPHINX_ROLE = re.compile(r":(?:mod|class|func|meth|attr|exc|data|obj):`")


def test_no_sphinx_roles_in_hand_written_modules() -> None:
    offenders = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        if path == GENERATED:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if SPHINX_ROLE.search(line):
                where = path.relative_to(ROOT)
                offenders.append(f"{where}:{number}: {line.strip()}")
    message = "Sphinx roles found; use Markdown code spans:\n" + "\n".join(offenders)
    assert not offenders, message
