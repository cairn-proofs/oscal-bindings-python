"""Typed Python data bindings for OSCAL (Open Security Controls Assessment Language).

The bindings read and write the eight OSCAL document types as Pydantic v2 models.
They are generated from the OSCAL 1.2.3 JSON Schema. `__oscal_schema_version__`
holds the exact OSCAL release.

Install the package. The `yaml` extra adds the YAML operations. The base install
has one runtime dependency, `pydantic`.

```bash
pip install oscal-bindings
pip install "oscal-bindings[yaml]"
```

Example:

    >>> from oscal_bindings import parse_oscal_file, serialize_oscal
    >>> doc = parse_oscal_file("catalog.json")
    >>> json_str = serialize_oscal(doc)

The package `oscal_bindings` re-exports `oscal_bindings.v1`. A name that you
reach through either path is the same object, so `isinstance` agrees. The
reference for each class and function is on the page of `oscal_bindings.v1`.
The page of `oscal_bindings.v1.models` documents each generated model.

For the full guide, read the
[README](https://github.com/cairn-proofs/oscal-bindings-python#readme).
"""

from oscal_bindings import v1 as _v1

# The curated public surface, bounded by ``oscal_bindings.v1.__all__``. A plain
# star import is safe: the YAML operations import PyYAML only when called
# (design Decision 5), so a base install without the ``yaml`` extra imports fine.
# A star import also keeps the names statically typed.
from oscal_bindings.v1 import *  # noqa: F403

# Not in ``v1.__all__`` (it is metadata, not API), so re-exported explicitly.
from oscal_bindings.v1 import __oscal_schema_version__ as __oscal_schema_version__

# Generated model names: star-imported from the models module directly rather
# than from ``oscal_bindings.v1``, both for provenance (the names visibly come
# from where they are defined) and because ``oscal_bindings.v1`` defines
# ``__all__``, which would bound the star-import to the curated surface and drop
# the ~180 model names this line exists to carry.
from oscal_bindings.v1.models import *  # noqa: F403

__all__ = list(_v1.__all__)
