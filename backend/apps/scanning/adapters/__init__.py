"""Adapter registry. Importing this package is what makes an ecosystem exist.

Each adapter module registers itself on import (`base.register`), so the
registry is populated as a side effect of this file's imports and nothing else
in the codebase enumerates ecosystems by hand. Phase 6 added exactly the one
line below for PyPI, and pre-scan validation, the scanner, the scoring engine
and the API all learned about it without being touched — which is the diff
`docs/adapter_soundness.md` shows.
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
    matches_workspace_globs,
    supported_ecosystems,
    supported_manifest_names,
)
from .npm import NpmAdapter, npm_adapter
from .pypi import PypiAdapter, pypi_adapter

__all__ = [
    "VENDOR_DIRS",
    "DepSpec",
    "DependencyAdapter",
    "ManifestParseError",
    "NpmAdapter",
    "PackageFacts",
    "PypiAdapter",
    "adapter_for_path",
    "all_adapters",
    "get_adapter",
    "matches_workspace_globs",
    "npm_adapter",
    "pypi_adapter",
    "supported_ecosystems",
    "supported_manifest_names",
]
