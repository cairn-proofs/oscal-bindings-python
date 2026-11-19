# Installation and versions

Requires Python 3.11+ (tested on 3.11–3.15) and Pydantic 2.14.2+ (below 3).

```bash
pip install oscal-bindings
# or
uv add oscal-bindings
```

The distribution is `oscal-bindings`; the import package is `oscal_bindings`.

YAML parse and serialize are an optional feature. Install the `yaml` extra to add them:

```bash
pip install "oscal-bindings[yaml]"
# or
uv add "oscal-bindings[yaml]"
```

The base install keeps a single runtime dependency (`pydantic`). Every import works without the extra. A call to a YAML operation without the extra raises `ImportError` with an install hint.

To install from a local checkout (e.g., as a `uv` workspace path dependency):

```bash
uv add ../oscal-bindings-python
# or
pip install -e ../oscal-bindings-python
```

To install directly from a Git tag, branch, or commit:

```bash
pip install "git+https://github.com/cairn-proofs/oscal-bindings-python.git@main"
```

## Import paths

The bindings live under a namespace scoped to the OSCAL **major** version:

```python
from oscal_bindings.v1 import parse_oscal, OscalDoc, Catalog
```

The top-level package re-exports the current major version, so `from oscal_bindings import parse_oscal` (and `oscal_bindings.models`, `oscal_bindings.parser`, `oscal_bindings.extensions`) resolves to the same objects:

```python
import oscal_bindings
import oscal_bindings.v1

oscal_bindings.Catalog is oscal_bindings.v1.models.Catalog   # True
```

Examples below use the shorter top-level path. Importing from `oscal_bindings.v1` is equivalent and states which OSCAL major version your code is written against.

OSCAL is backward-compatible within a major version, so a routine 1.x schema refresh regenerates `v1` in place and never changes your imports. Only OSCAL 2.0 would introduce a second namespace.

## Which OSCAL release?

`__oscal_schema_version__` reports the exact release the models were generated from:

```python
from oscal_bindings import __oscal_schema_version__

__oscal_schema_version__      # '1.2.3'
```

Worth checking, because models are strict about unknown fields: a document from a newer 1.x release than the one the models come from can fail validation on a field these bindings have never seen. The constant makes that gap visible rather than a mystery.
