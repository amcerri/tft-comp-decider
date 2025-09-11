"""
Stage-aware scoring engine for TFT builds.

Overview
--------
Compute a transparent score for a build given the user's current inventory.
The score combines:
- Champion presence across early/mid/late comps (weighted by current stage).
- Item component alignment using an ordered priority list (+ optional BiS bonus).
- A small prior derived from the build's tier and rank within the tier.

Design
------
- Keep the engine explainable and deterministic; avoid black-box ML.
- Depend only on previously defined internal modules (types/models/solver/logging).
- Provide a single entry point ``score_build`` that returns a structured breakdown.

Integration
-----------
Used by the Streamlit UI to rank builds and to display the reasoning (coverage,
core units, stage weight, etc.). This module is safe to import in tests and in
CLI/REPL usage.

Usage
-----
>>> from tft_decider.core.models import Build, Inventory
>>> from tft_decider.core.scoring import score_build
>>> b = Build(id="demo", name="Demo", tier="A", tier_rank=1, patch="15.4",
...           early_comp=["Gnar"], mid_comp=["Sivir"], late_comp=["Jhin"],
...           item_priority_components=["Recurve Bow"])
>>> inv = Inventory(units={"Gnar": 1, "Sivir": 1}, items_components={"Recurve Bow": 1}, stage="3-2")
>>> score = score_build(b, inv)
>>> round(score.total, 3) >= 0
True
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Mapping, Optional, Sequence

from tft_decider.core.models import Build, Inventory
from tft_decider.core.types import StageBucket, stage_bucket
from tft_decider.infra.logging import generate_thread_id, logger_for
from tft_decider.core.solver import (
    AssignmentResult,
    assign_components_by_priority,
    CraftResult,
    craftable_bis_items,
)

__all__: Final[list[str]] = [
    "ScoreBreakdown",
    "score_build",
]


# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------
# Champion presence weights by current stage bucket.
STAGE_WEIGHTS: Final[dict[StageBucket, dict[str, float]]] = {
    StageBucket.EARLY: {"early": 0.60, "mid": 0.25, "late": 0.15},
    StageBucket.MID: {"early": 0.20, "mid": 0.55, "late": 0.25},
    StageBucket.LATE: {"early": 0.10, "mid": 0.25, "late": 0.65},
}

# Prior for tier meta strength; small rank bonus within the tier.
TIER_PRIOR: Final[dict[str, float]] = {"S": 1.0, "A": 0.6, "B": 0.3, "C": 0.0, "X": -0.2}
MAX_RANK_BONUS: Final[float] = 0.20  # soft boost for better rank inside the tier

# Final score weights (champions/items/prior).
WEIGHTS: Final[dict[str, float]] = {"champions": 0.50, "items": 0.40, "prior": 0.10}

# Cap for the BiS crafting bonus applied on top of component coverage.
MAX_BIS_BONUS: Final[float] = 0.15


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ScoreBreakdown:
    """Hold a detailed breakdown of a build score.

    Attributes:
        total: Final combined score in ``[0, 1]``.
        champions: Champion-related component of the score in ``[0, 1]``.
        items: Item-related component of the score in ``[0, 1]``.
        prior: Tier/rank prior in ``[0, 1]``.
        stage_bucket: The bucket used to weigh early/mid/late.
        details: Arbitrary extra details for UI (counts, coverage, etc.).
    """

    total: float
    champions: float
    items: float
    prior: float
    stage_bucket: StageBucket
    details: dict[str, Any]


# ---------------------------------------------------------------------------
# Champion presence scoring
# ---------------------------------------------------------------------------

def _presence_ratio(have_units: Mapping[str, int], target: Sequence[str]) -> float:
    """Return the fraction of target units that are present (stars > 0).

    Args:
        have_units: Mapping from champion name to star level.
        target: Target champion list.

    Returns:
        A float in ``[0, 1]``.
    """

    if not target:
        return 0.0
    hit = sum(1 for name in target if have_units.get(name, 0) > 0)
    return hit / len(target)


def _core_units_score(build: Build, inv: Inventory) -> float:
    """Compute averaged progress toward core unit goals.

    Required units that are missing contribute ``0`` (no extra penalty to keep
    the score bounded in ``[0, 1]``). Present units contribute proportionally to
    their star goal, capped at 1.0.
    """

    if not build.core_units:
        return 0.0
    accum = 0.0
    for cu in build.core_units:
        have = inv.units.get(cu.name, 0)
        contrib = min(have / max(cu.star_goal, 1), 1.0) if have > 0 else 0.0
        accum += contrib
    return accum / len(build.core_units)


def _score_champions(build: Build, inv: Inventory, bucket: StageBucket) -> dict[str, float]:
    """Return champion-related partial scores.

    The result includes ``stage_presence`` (weighted across early/mid/late) and
    ``core_progress`` (averaged core unit progress). The caller is responsible
    for combining them into a single ``champions`` value.
    """

    weights = STAGE_WEIGHTS[bucket]
    s_early = _presence_ratio(inv.units, build.early_comp)
    s_mid = _presence_ratio(inv.units, build.mid_comp)
    s_late = _presence_ratio(inv.units, build.late_comp)
    stage_presence = (
        weights["early"] * s_early + weights["mid"] * s_mid + weights["late"] * s_late
    )
    core_progress = _core_units_score(build, inv)
    return {
        "stage_presence": max(0.0, min(1.0, stage_presence)),
        "core_progress": max(0.0, min(1.0, core_progress)),
        "early": s_early,
        "mid": s_mid,
        "late": s_late,
    }


# ---------------------------------------------------------------------------
# Item scoring
# ---------------------------------------------------------------------------

def _score_items(
    build: Build,
    inv: Inventory,
    *,
    recipes: Optional[Mapping[str, Sequence[str]]] = None,
    thread_id: Optional[str] = None,
) -> dict[str, float | AssignmentResult | CraftResult]:
    """Return item-related partial scores and artifacts.

    The base is the coverage of the ordered component priority list.
    Optionally, a small bonus is added for BiS that are immediately craftable
    according to the provided ``recipes``.
    """

    assignment = assign_components_by_priority(
        build.item_priority_components,
        inv.items_components,
        thread_id=thread_id,
    )

    base = assignment.coverage
    bis_bonus = 0.0
    craft: Optional[CraftResult] = None

    if recipes and build.bis_items:
        # Try to greedily craft requested BiS items to provide a small bonus.
        craft = craftable_bis_items(build.bis_items, recipes, inv.items_components, thread_id=thread_id)
        desired_total = sum(len(v) for v in build.bis_items.values()) or 1
        ratio = min(1.0, len(craft.crafted) / desired_total)
        bis_bonus = min(MAX_BIS_BONUS, 0.5 * MAX_BIS_BONUS * ratio + (0.5 * MAX_BIS_BONUS if craft.crafted else 0.0))

    items_score = max(0.0, min(1.0, base + bis_bonus))

    return {
        "items_score": items_score,
        "assignment": assignment,
        "bis_bonus": bis_bonus,
        "crafted": craft.crafted if craft else [],
    }


# ---------------------------------------------------------------------------
# Prior
# ---------------------------------------------------------------------------

def _tier_prior(tier: str, tier_rank: int) -> float:
    """Compute a small prior based on tier and rank within tier.

    Args:
        tier: One of ``S/A/B/C/X``.
        tier_rank: Rank inside the tier (1 = best).

    Returns:
        A float in ``[0, 1]`` representing the prior strength.
    """

    base = TIER_PRIOR.get(tier.upper(), 0.0)
    # Convert rank to a 0..1 scale where 1 is best; assume up to ~10 per tier.
    rank_quality = max(0.0, min(1.0, 1.0 - (max(1, tier_rank) - 1) / 10.0))
    bonus = MAX_RANK_BONUS * rank_quality
    return max(0.0, min(1.0, base + bonus))


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def score_build(
    build: Build,
    inv: Inventory,
    *,
    recipes: Optional[Mapping[str, Sequence[str]]] = None,
    weights: Optional[Mapping[str, float]] = None,
    thread_id: Optional[str] = None,
) -> ScoreBreakdown:
    """Compute the final score and a breakdown for a build.

    Args:
        build: The build to score.
        inv: The user's current inventory.
        recipes: Optional mapping from completed item → component recipe to
            enable BiS crafting bonus. If omitted, the score uses component
            coverage only.
        weights: Optional override for ``{"champions": float, "items": float, "prior": float}``.
        thread_id: Optional correlation ID for structured logging.

    Returns:
        A :class:`ScoreBreakdown` with the final score and its components.
    """

    log = logger_for(component="core.scoring", event="score_build", thread_id=thread_id or generate_thread_id())

    bucket = stage_bucket(inv.stage)
    champ_parts = _score_champions(build, inv, bucket)
    # Combine champion parts: emphasize stage presence with a smaller core bonus.
    champions_score = max(0.0, min(1.0, 0.7 * champ_parts["stage_presence"] + 0.3 * champ_parts["core_progress"]))

    item_parts = _score_items(build, inv, recipes=recipes, thread_id=log._context.get("thread_id"))  # type: ignore[attr-defined]
    items_score = float(item_parts["items_score"])  # type: ignore[assignment]

    prior_score = _tier_prior(build.tier, build.tier_rank)

    w = dict(WEIGHTS)
    if weights:
        # Apply a lightweight override while keeping absent keys at defaults.
        w.update({k: float(v) for k, v in weights.items() if k in w})

    total = (
        w["champions"] * champions_score + w["items"] * items_score + w["prior"] * prior_score
    )
    total = max(0.0, min(1.0, total))

    details: dict[str, Any] = {
        "early": champ_parts["early"],
        "mid": champ_parts["mid"],
        "late": champ_parts["late"],
        "stage_presence": champ_parts["stage_presence"],
        "core_progress": champ_parts["core_progress"],
        "assignment": item_parts["assignment"],
        "bis_bonus": item_parts["bis_bonus"],
        "crafted": item_parts["crafted"],
    }

    log.info(
        "Build scored",
        id=build.id,
        name=build.name,
        stage=str(inv.stage),
        stage_bucket=bucket.value,
        champions=round(champions_score, 3),
        items=round(items_score, 3),
        prior=round(prior_score, 3),
        total=round(total, 3),
    )

    return ScoreBreakdown(
        total=total,
        champions=champions_score,
        items=items_score,
        prior=prior_score,
        stage_bucket=bucket,
        details=details,
    )