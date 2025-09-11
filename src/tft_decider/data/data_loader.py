"""
Builds loader for YAML-defined TFT compositions.

Overview
--------
Load and validate build definitions from local YAML files. Each file describes a
single build (core units, early/mid/late comps, item component priorities, links,
notes). The loader returns Pydantic-validated models for downstream scoring and UI.

Design
------
- Keep this module self-contained (stdlib + pydantic + yaml + internal types/models).
- Provide file-level and directory-level loaders with structured logging.
- Enforce unique build IDs when loading a directory (configurable via ``strict_ids``).
- Avoid importing solver/scoring to prevent circular dependencies.

Integration
-----------
Used by the Streamlit app and tests to populate the in-memory library of builds.
The function ``load_builds_from_dir`` expects YAML files under ``data/builds/``.

Usage
-----
>>> from tft_decider.data.data_loader import load_build_from_yaml, load_builds_from_dir
>>> b = load_build_from_yaml("data/builds/sniper_squad.yaml")
>>> builds = load_builds_from_dir("data/builds")
>>> len(builds) >= 1
True
"""

from __future__ import annotations

from pathlib import Path
from typing import Final, Iterable, Optional

import yaml
from pydantic import ValidationError

from tft_decider.core.exceptions import DataLoadError, InvalidBuildError
from tft_decider.core.models import Build
from tft_decider.infra.logging import generate_thread_id, logger_for

__all__: Final[list[str]] = [
    "load_build_from_yaml",
    "load_builds_from_dir",
    "index_builds_by_id",
    "sort_builds_by_meta",
]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_TIER_ORDER: Final[dict[str, int]] = {"S": 0, "A": 1, "B": 2, "C": 3, "X": 4}


def _iter_yaml_files(directory: Path) -> Iterable[Path]:
    """Yield YAML file paths (``.yaml`` and ``.yml``) from a directory.

    Args:
        directory: The directory to scan (non-recursive).

    Yields:
        Paths to YAML files in alphabetical order.
    """

    # Non-recursive scan; sorted for deterministic load order.
    for pattern in ("*.yaml", "*.yml"):
        for p in sorted(directory.glob(pattern)):
            if p.is_file():
                yield p


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_build_from_yaml(path: str | Path, *, thread_id: Optional[str] = None) -> Build:
    """Load and validate a single build from a YAML file.

    Args:
        path: Filesystem path to the build YAML.
        thread_id: Optional correlation ID used in structured logs.

    Returns:
        A validated :class:`Build` instance.

    Raises:
        DataLoadError: If the file cannot be opened or parsed as YAML.
        InvalidBuildError: If the content fails schema/semantic validation.
    """

    log = logger_for(component="data.builds", event="load_file", thread_id=thread_id or generate_thread_id())
    p = Path(path)
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        log.error("Build file not found", path=str(p))
        raise DataLoadError(path=str(p), reason="file not found") from exc
    except OSError as exc:
        log.error("Failed to open build file", path=str(p), error=str(exc))
        raise DataLoadError(path=str(p), reason=str(exc)) from exc

    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - parser variations
        log.error("Invalid YAML syntax", path=str(p), error=str(exc))
        raise DataLoadError(path=str(p), reason="invalid YAML") from exc

    try:
        build = Build(**data)
    except ValidationError as exc:
        log.error("Build validation error", path=str(p), error=str(exc))
        raise InvalidBuildError(build_id=data.get("id"), errors=[str(exc)]) from exc
    except Exception as exc:  # pragma: no cover - safety net
        log.error("Unexpected error while validating build", path=str(p), error=str(exc))
        raise InvalidBuildError(build_id=data.get("id"), errors=[str(exc)]) from exc

    log.info(
        "Build loaded",
        path=str(p),
        id=build.id,
        name=build.name,
        tier=build.tier,
        tier_rank=build.tier_rank,
        patch=build.patch,
    )
    return build


def load_builds_from_dir(
    directory: str | Path,
    *,
    strict_ids: bool = True,
    thread_id: Optional[str] = None,
) -> list[Build]:
    """Load and validate all builds from a directory.

    Args:
        directory: Folder that contains build YAML files (non-recursive).
        strict_ids: If ``True``, raise on duplicate build IDs; otherwise keep the
            first occurrence and log a warning for subsequent duplicates.
        thread_id: Optional correlation ID used in structured logs.

    Returns:
        A list of validated :class:`Build` instances.

    Raises:
        DataLoadError: If the directory is missing or unreadable.
        InvalidBuildError: If duplicate IDs are found and ``strict_ids`` is ``True``.
    """

    log = logger_for(component="data.builds", event="load_dir", thread_id=thread_id or generate_thread_id())
    d = Path(directory)
    if not d.exists() or not d.is_dir():
        log.error("Builds directory not found or not a directory", path=str(d))
        raise DataLoadError(path=str(d), reason="directory not found")

    builds: list[Build] = []
    seen_ids: dict[str, Path] = {}
    duplicates: list[str] = []

    for file_path in _iter_yaml_files(d):
        b = load_build_from_yaml(file_path, thread_id=log._context.get("thread_id"))  # type: ignore[attr-defined]
        if b.id in seen_ids:
            msg = f"duplicate build id '{b.id}' in {file_path} (already defined in {seen_ids[b.id]})"
            if strict_ids:
                duplicates.append(msg)
            else:
                log.warning("Duplicate build id encountered; keeping first occurrence", id=b.id, path=str(file_path))
                continue
        else:
            seen_ids[b.id] = file_path
            builds.append(b)

    if duplicates and strict_ids:
        log.error("Duplicate build ids found", count=len(duplicates))
        raise InvalidBuildError(build_id=None, errors=duplicates)

    log.info("Builds directory loaded", path=str(d), count=len(builds))
    return builds


def index_builds_by_id(builds: list[Build]) -> dict[str, Build]:
    """Return a dictionary keyed by build id for fast lookup.

    Args:
        builds: The list of builds to index.

    Returns:
        Mapping from build id to build model. If duplicate ids are present, the
        last one wins (callers should normally load with ``strict_ids=True``).
    """

    return {b.id: b for b in builds}


def sort_builds_by_meta(builds: list[Build]) -> list[Build]:
    """Return a new list sorted by tier strength and rank within the tier.

    Ordering heuristic: S > A > B > C > X, then ascending ``tier_rank``.

    Args:
        builds: The list of builds to sort.

    Returns:
        A new list of builds sorted by the described heuristic.
    """

    def _key(b: Build) -> tuple[int, int, str]:
        return (_TIER_ORDER.get(b.tier, 99), b.tier_rank, b.name.lower())

    return sorted(builds, key=_key)