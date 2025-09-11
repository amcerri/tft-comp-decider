

"""
Champion analytics.

Overview
--------
Compute relevance (heat) scores for champions across all configured builds. The
score is normalized to [0.0, 1.0] and can be used by the UI to color champion
selection boxes (green = more relevant, red = unused).

Design
------
- Aggregate contributions per champion from all builds.
- Weight by build tier and by the section where the champion appears
  (late/final > mid > early).
- Apply a small multiplier when the champion is marked as a core unit.
- Normalize by the maximum accumulated value to obtain [0, 1].

Integration
-----------
Used by the Streamlit UI to produce a heat map for champion selectors.
This module is self-contained and does not depend on UI code.

Usage
-----
>>> from tft_decider.core.analytics import compute_champion_heat
>>> scores = compute_champion_heat(builds)
>>> scores.get("Xayah", 0.0)
0.83
"""

from __future__ import annotations

from collections import defaultdict
from typing import Final, Iterable
from uuid import uuid4

from tft_decider.infra.logging import logger_for
from tft_decider.core.models import Build

__all__: Final[list[str]] = ["compute_champion_heat"]

# --- Weights ---------------------------------------------------------------
TIER_WEIGHTS: Final[dict[str, float]] = {
    "S": 1.00,
    "A": 0.85,
    "B": 0.70,
    "C": 0.50,
    "X": 0.35,  # situational
}

SECTION_WEIGHTS: Final[dict[str, float]] = {
    "late": 1.00,  # late_comp (or explicit late/full)
    "final": 1.00,  # comp (final/default)
    "mid": 0.60,
    "early": 0.35,
}

CORE_MULTIPLIER: Final[float] = 1.25


logger = logger_for(component="core.analytics", event="init", thread_id="module")


def _iter_names(values: Iterable[object]) -> list[str]:
    """Extract champion names from a heterogenous iterable.

    Accepts strings or small objects with a ``name`` attribute.
    """
    names: list[str] = []
    for v in values or []:  # type: ignore[truthy-bool]
        if isinstance(v, str):
            names.append(v)
        else:
            # Fallback to attribute or string conversion
            name = getattr(v, "name", None)
            names.append(str(name if name is not None else v))
    return names


def compute_champion_heat(builds: list[Build]) -> dict[str, float]:
    """Compute a normalized relevance score per champion.

    The score aggregates appearances across all builds with the following
    weighting scheme:

    - Build tier weight: S=1.00, A=0.85, B=0.70, C=0.50, X=0.35.
    - Section weight: late/final=1.00, mid=0.60, early=0.35.
    - Core unit multiplier: ×1.25 when a champion is marked as core in a build.

    Args:
        builds: The list of build definitions to analyze.

    Returns:
        A mapping ``{champion_name: score}`` with scores in the inclusive range
        ``[0.0, 1.0]``. Missing champions will not be present in the mapping.
    """
    thread_id = uuid4().hex
    acc: defaultdict[str, float] = defaultdict(float)

    for b in builds:
        tier_w = TIER_WEIGHTS.get((b.tier or "").upper(), 0.50)

        # Determine core names for the build (if present)
        core_names = set(_iter_names(getattr(b, "core_units", []) or []))

        # Late / Final / Mid / Early contributions
        sections = [
            ("late", _iter_names(getattr(b, "late_comp", []) or [])),
            ("final", _iter_names(getattr(b, "comp", []) or [])),
            ("mid", _iter_names(getattr(b, "mid_comp", []) or [])),
            ("early", _iter_names(getattr(b, "early_comp", []) or [])),
        ]
        for section_name, names in sections:
            sec_w = SECTION_WEIGHTS.get(section_name, 0.0)
            if sec_w <= 0.0:
                continue
            base = tier_w * sec_w
            for name in names:
                weight = base * (CORE_MULTIPLIER if name in core_names else 1.0)
                acc[name] += weight

    if not acc:
        logger.bind(component="core.analytics", event="champion_heat", thread_id=thread_id).info(
            "No champions aggregated for heat computation", builds=len(builds)
        )
        return {}

    max_val = max(acc.values())
    if max_val <= 0.0:
        logger.bind(component="core.analytics", event="champion_heat", thread_id=thread_id).info(
            "Non-positive max value in heat accumulator", max_val=max_val
        )
        return {k: 0.0 for k in acc.keys()}

    normalized = {k: (v / max_val) for k, v in acc.items()}
    logger.bind(component="core.analytics", event="champion_heat", thread_id=thread_id).info(
        "Champion heat computed", champions=len(normalized), max_score=1.0
    )
    return normalized
