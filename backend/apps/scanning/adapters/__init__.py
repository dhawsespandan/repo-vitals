"""Adapter registry. Importing this package is what makes an ecosystem exist.

Each adapter module registers itself on import (`base.register`), so the
registry is populated as a side effect of this file's imports and nothing else
in the codebase enumerates ecosystems by hand. Phase 6 adds one line here for
PyPI, and pre-scan validation, the scanner and the API all learn about it
without being touched — which is the diff `docs/adapter_soundness.md` has to
be able to show.
"""

from .base import (
    VENDOR_DIRS,
    DependencyAdapter,
    DepSpec,
    ManifestParseError,
    PackageFacts,
    adapter_for_path,
    all_adapters,
    get_adapter,
    supported_ecosystems,
    supported_manifest_names,
)
from .npm import NpmAdapter, npm_adapter

__all__ = [
    "VENDOR_DIRS",
    "DepSpec",
    "DependencyAdapter",
    "ManifestParseError",
    "NpmAdapter",
    "PackageFacts",
    "adapter_for_path",
    "all_adapters",
    "get_adapter",
    "npm_adapter",
    "supported_ecosystems",
    "supported_manifest_names",
]
