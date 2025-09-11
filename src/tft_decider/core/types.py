"""
Common type aliases and enums for the TFT Comp Decider.

Overview
--------
Centralize small, dependency-free contracts shared across the project:
- Type aliases for domain strings (champions, items, augments, etc.).
- Enums for message severity and stage buckets.
- Stage utilities for parsing and comparing stage strings like "3-2".

Design
------
- Keep this module **standalone** (stdlib only) to avoid import cycles.
- Prefer explicit, readable enums over magic strings.
- Provide tiny helpers for stage handling since multiple modules need them.

Integration
-----------
Imported by core components (models, scoring, notes) for shared types and
helpers. Safe to import early; no side effects.

Usage
-----
>>> from tft_decider.core.types import StageBucket, stage_bucket, stage_ge
>>> stage_bucket("2-1") is StageBucket.EARLY
True
>>> stage_bucket("3-2") is StageBucket.MID
True
>>> stage_ge("4-1", "3-2")
True
"""

from __future__ import annotations

from enum import Enum
from typing import Final, TypeAlias

# ---------------------------------------------------------------------------
# Type aliases (domain strings)
# ---------------------------------------------------------------------------
ChampionName: TypeAlias = str
ComponentName: TypeAlias = str
CompletedItemName: TypeAlias = str
AugmentName: TypeAlias = str
TraitName: TypeAlias = str
BuildId: TypeAlias = str
UrlStr: TypeAlias = str
StageString: TypeAlias = str  # e.g., "2-1", "3-2", "4-5"
JsonDict: TypeAlias = dict[str, object]

__all__: Final[list[str]] = [
    # Aliases
    "ChampionName",
    "ComponentName",
    "CompletedItemName",
    "AugmentName",
    "TraitName",
    "BuildId",
    "UrlStr",
    "StageString",
    "JsonDict",
    # Enums
    "Severity",
    "StageBucket",
    # Stage helpers
    "parse_stage",
    "stage_bucket",
    "stage_ge",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class Severity(str, Enum):
    """Represent message severity for notes/banners.

    Values mirror common UI semantics; ordered loosely by importance.
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class StageBucket(str, Enum):
    """Represent coarse buckets of the game stage."""

    EARLY = "early"
    MID = "mid"
    LATE = "late"


# ---------------------------------------------------------------------------
# Stage utilities
# ---------------------------------------------------------------------------
_EARLY_CUTOFF: Final[tuple[int, int]] = (3, 1)  # up to and including 3-1 → EARLY
_MID_CUTOFF: Final[tuple[int, int]] = (4, 1)    # up to and including 4-1 → MID, else LATE


def parse_stage(stage: StageString) -> tuple[int, int]:
    """Parse a stage string like "3-2" into a (round, step) tuple.

    Args:
        stage: The stage string in the form ``"R-S"``, where both parts are integers.

    Returns:
        A tuple ``(round, step)``.

    Raises:
        ValueError: If the input is not a valid ``R-S`` pattern of integers.
    """

    if not isinstance(stage, str) or "-" not in stage:
        raise ValueError("stage must be a 'R-S' string, e.g., '3-2'")
    left, right = stage.split("-", 1)
    try:
        r = int(left.strip())
        s = int(right.strip())
    except ValueError as exc:  # pragma: no cover - trivial guard
        raise ValueError("stage must contain integer parts, e.g., '3-2'") from exc
    if r <= 0 or s < 0:
        raise ValueError("stage parts must be non-negative (round>0, step>=0)")
    return r, s


def stage_bucket(stage: StageString) -> StageBucket:
    """Map a stage string to a coarse bucket: early, mid or late.

    Heuristic (transparent and easy to tweak):
    - ``<= 3-1`` → EARLY
    - ``<= 4-1`` → MID
    - otherwise → LATE

    Args:
        stage: The stage string (e.g., ``"2-1"``, ``"3-2"``, ``"4-5"``).

    Returns:
        The corresponding :class:`StageBucket`.
    """

    r, s = parse_stage(stage)
    if (r, s) <= _EARLY_CUTOFF:
        return StageBucket.EARLY
    if (r, s) <= _MID_CUTOFF:
        return StageBucket.MID
    return StageBucket.LATE


def stage_ge(a: StageString, b: StageString) -> bool:
    """Return whether stage ``a`` is greater-than-or-equal to stage ``b``.

    Args:
        a: The left-hand stage string.
        b: The right-hand stage string to compare against.

    Returns:
        ``True`` if ``a >= b`` in lexicographic stage ordering, ``False`` otherwise.
    """

    return parse_stage(a) >= parse_stage(b)