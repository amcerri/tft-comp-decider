"""
TFT Decider package initializer.

Overview
--------
Provide package metadata and lightweight helpers used across the project.
This module intentionally avoids importing subpackages to keep imports side-effect free.

Design
------
- Expose a semantic version string via `__version__`.
- Declare a minimal public API through `__all__`.
- Avoid runtime imports of optional dependencies or internal modules to prevent import cycles.

Integration
-----------
Imported implicitly as `tft_decider` when any submodule is used.
Has no side effects and is safe to import early during application startup.

Usage
-----
>>> import tft_decider
>>> tft_decider.__version__
'0.1.0'
>>> tft_decider.package_info()["repository"]
'https://github.com/amcerri/tft-comp-decider'
"""

from typing import Final

__version__: Final[str] = "0.1.0"
"""Semantic version of the package.

The value is intentionally duplicated from `pyproject.toml` to keep this module
self-contained and importable without reading package metadata at runtime.
"""

REPOSITORY_URL: Final[str] = "https://github.com/amcerri/tft-comp-decider"
"""Canonical repository URL for this project."""

__all__: Final[list[str]] = ["__version__", "package_info"]
"""Public symbols re-exported by the package root."""


def package_info() -> dict[str, str]:
    """Return basic package information.

    Returns:
        A mapping with the keys ``name``, ``version`` and ``repository`` that can be
        displayed in diagnostics, logs or a UI "About" dialog.
    """

    return {
        "name": "tft-comp-decider",
        "version": __version__,
        "repository": REPOSITORY_URL,
    }