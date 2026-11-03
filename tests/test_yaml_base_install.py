"""Tests for the YAML surface on a base install, and for its import paths.

A base install has no ``yaml`` extra. Every import path of the package must
still work, and only a call to a YAML operation raises the install hint (design
Decision 5). Each check runs in a fresh interpreter where a ``sys.meta_path``
finder blocks ``yaml``.
"""

import inspect
import subprocess
import sys
import textwrap

import pytest

import oscal_bindings
import oscal_bindings.extensions
import oscal_bindings.v1
import oscal_bindings.v1.extensions
from oscal_bindings.v1.extensions import yaml_io

YAML_NAMES = ("parse_oscal_yaml", "parse_oscal_yaml_file", "serialize_oscal_yaml")


def _run_without_yaml(body: str) -> subprocess.CompletedProcess[str]:
    """Run ``body`` in a fresh interpreter where importing ``yaml`` fails."""
    prelude = textwrap.dedent(
        """\
        import sys, importlib.abc

        class _BlockYaml(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path, target=None):
                if name == "yaml" or name.startswith("yaml.") or name == "_yaml":
                    raise ImportError(f"No module named {name!r}", name=name)
                return None

        sys.meta_path.insert(0, _BlockYaml())
        for _m in list(sys.modules):
            if _m == "yaml" or _m.startswith("yaml."):
                del sys.modules[_m]
        """
    )
    return subprocess.run(  # noqa: S603 - fixed interpreter, no shell
        [sys.executable, "-c", prelude + textwrap.dedent(body)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "stmt",
    [
        "import oscal_bindings",
        "from oscal_bindings import *",
        "import oscal_bindings.extensions",
        "from oscal_bindings.extensions import *",
        "import oscal_bindings.v1",
        "from oscal_bindings.v1 import *",
        "from oscal_bindings.v1.extensions import *",
        "import oscal_bindings.v1.extensions.yaml_io",
        "from oscal_bindings import parse_oscal, OscalDoc, make_hash, parse_oscal_yaml",
    ],
)
def test_import_path_works_without_yaml(stmt: str) -> None:
    proc = _run_without_yaml(
        f"{stmt}\n"
        "assert 'yaml' not in sys.modules, 'PyYAML was imported'\n"
        "print('ok')\n"
    )
    assert proc.returncode == 0, proc.stderr
    assert "ok" in proc.stdout


@pytest.mark.parametrize("name", YAML_NAMES)
def test_calling_a_yaml_op_raises_the_install_hint(name: str) -> None:
    arg = {
        "parse_oscal_yaml": '"catalog: {}"',
        "parse_oscal_yaml_file": '"x.yaml"',
    }.get(name, "None")
    proc = _run_without_yaml(
        f"""
        import oscal_bindings
        try:
            oscal_bindings.{name}({arg})
        except ImportError as exc:
            print("HINT" if "oscal-bindings[yaml]" in str(exc) else f"NO-HINT {{exc}}")
        else:
            print("NO-RAISE")
        """
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "HINT", proc.stdout


@pytest.mark.parametrize("name", YAML_NAMES)
def test_every_import_path_gives_the_same_function(name: str) -> None:
    func = getattr(yaml_io, name)
    for module in (
        oscal_bindings,
        oscal_bindings.v1,
        oscal_bindings.extensions,
        oscal_bindings.v1.extensions,
    ):
        assert getattr(module, name) is func, module.__name__
        assert name in module.__all__, module.__name__


@pytest.mark.parametrize("name", YAML_NAMES)
def test_public_function_carries_the_full_docstring(name: str) -> None:
    # pdoc publishes these docstrings, so each one documents the contract.
    doc = inspect.getdoc(getattr(oscal_bindings, name)) or ""
    assert "Raises:" in doc
    assert "yaml" in doc
