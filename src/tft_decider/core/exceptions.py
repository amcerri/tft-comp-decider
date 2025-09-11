"""
Domain-specific exceptions for the TFT Comp Decider.

Overview
--------
Provide a small hierarchy of typed exceptions to represent recoverable and
actionable errors across the project (data loading, validation, configuration,
solver/scoring issues, and not-found conditions).

Design
------
- Keep the hierarchy minimal and dependency-free (stdlib only).
- Every exception carries **context fields** to aid logging and debugging.
- The base class implements a clear ``__str__`` to surface the context.

Integration
-----------
Raise these exceptions from data loaders, scoring/solver logic, and UI glue.
Catch at UI boundaries to surface user-friendly messages while logging context.

Usage
-----
>>> raise DataLoadError(path="data/builds/foo.yaml", reason="malformed YAML")
Traceback (most recent call last):
...
DataLoadError: Failed to load data file: path='data/builds/foo.yaml'; reason='malformed YAML'
"""

from __future__ import annotations

from typing import Final, Iterable

__all__: Final[list[str]] = [
    "TFTDeciderError",
    "ConfigurationError",
    "DataLoadError",
    "CatalogLoadError",
    "CatalogValidationError",
    "InvalidBuildError",
    "NotFoundError",
    "SolverError",
    "ScoringError",
]


class TFTDeciderError(Exception):
    """Base class for all domain errors in this project.

    Subclasses should attach contextual attributes and rely on the default
    ``__str__`` provided here, which renders the class name, main message,
    and any non-empty context as ``key='value'`` pairs.
    """

    #: Default human-readable message used when no explicit message is provided.
    default_message: str = "An error occurred"

    def __init__(self, message: str | None = None, **context: object) -> None:
        self.message = message or self.default_message
        self.context = {k: v for k, v in context.items() if v is not None}
        super().__init__(self.message)

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        if not self.context:
            return self.message
        kv = "; ".join(f"{k}='{v}'" for k, v in self.context.items())
        return f"{self.message}: {kv}"


# ---------------------------------------------------------------------------
# Configuration & data loading
# ---------------------------------------------------------------------------
class ConfigurationError(TFTDeciderError):
    """Signal invalid or missing configuration."""

    default_message = "Invalid configuration"


class DataLoadError(TFTDeciderError):
    """Signal failures when loading arbitrary data files (e.g., YAML)."""

    default_message = "Failed to load data file"

    def __init__(self, path: str, reason: str | None = None) -> None:
        super().__init__(path=path, reason=reason)


class CatalogLoadError(TFTDeciderError):
    """Signal failures when loading the champions/items catalog."""

    default_message = "Failed to load catalog file"

    def __init__(self, path: str, reason: str | None = None) -> None:
        super().__init__(path=path, reason=reason)


class CatalogValidationError(TFTDeciderError):
    """Signal schema or semantic issues in a loaded catalog."""

    default_message = "Invalid catalog data"

    def __init__(self, errors: Iterable[str] | None = None) -> None:
        joined = "; ".join(errors) if errors else None
        super().__init__(errors=joined)


# ---------------------------------------------------------------------------
# Domain validation and lookups
# ---------------------------------------------------------------------------
class InvalidBuildError(TFTDeciderError):
    """Signal schema or semantic issues in a build definition."""

    default_message = "Invalid build definition"

    def __init__(self, build_id: str | None = None, errors: Iterable[str] | None = None) -> None:
        joined = "; ".join(errors) if errors else None
        super().__init__(build_id=build_id, errors=joined)


class NotFoundError(TFTDeciderError):
    """Represent missing domain entities (e.g., champion, item, build)."""

    default_message = "Entity not found"

    def __init__(self, kind: str, identifier: str) -> None:
        super().__init__(kind=kind, identifier=identifier)


# ---------------------------------------------------------------------------
# Engine (solver/scoring)
# ---------------------------------------------------------------------------
class SolverError(TFTDeciderError):
    """Signal issues while matching components to target priorities."""

    default_message = "Solver failure"


class ScoringError(TFTDeciderError):
    """Signal issues while computing scores for builds."""

    default_message = "Scoring failure"