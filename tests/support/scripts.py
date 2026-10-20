"""Load a module from ``scripts/`` in the test process.

``scripts/`` is not a package. A script there imports its siblings by plain
name (``from pinned_archive import ...``), which works when Python runs the
script, because the script's directory is the first entry of ``sys.path``.
``load_script`` gives the test process the same view: it registers the module
in ``sys.modules`` under its plain name and puts ``scripts/`` on ``sys.path``
only while the module executes, so sibling imports resolve to the same module
objects that the tests use.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType

SCRIPTS_DIR: Path = Path(__file__).resolve().parent.parent.parent / "scripts"


def load_script(name: str) -> ModuleType:
    """Return the module ``scripts/<name>.py``, loading it once per process."""
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = SCRIPTS_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        msg = f"Cannot load script module {path}"
        raise ImportError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    scripts_dir = str(SCRIPTS_DIR)
    sys.path.insert(0, scripts_dir)
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[name]
        raise
    finally:
        sys.path.remove(scripts_dir)
    return module
