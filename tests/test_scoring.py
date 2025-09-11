"""
Scoring and notes smoke tests.

Overview
--------
Provide minimal, deterministic tests that validate the scoring engine,
assignment coverage artifacts, and the notes/banners evaluation. These tests
use only local YAML data and the public APIs from core modules.

Design
------
- Keep assertions robust but not brittle to minor tuning changes.
- Favor readable setups using fixtures from ``conftest.py``.
- Avoid UI imports; test only core/data modules.

Integration
-----------
Run with ``pytest`` after installing dev dependencies. Tests rely on the
fixtures declared in ``tests/conftest.py``.

Usage
-----
>>> pytest -q
"""

from __future__ import annotations

from typing import Final

import pytest

from tft_decider.core.models import Inventory
from tft_decider.core.scoring import ScoreBreakdown, score_build
from tft_decider.core.notes import evaluate_notes

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_build(builds: list, build_id: str):
    """Return a build from ``builds`` by id.

    Args:
        builds: A list of build models.
        build_id: The target build id.

    Returns:
        The build instance.

    Raises:
        AssertionError: If not found (tests should guarantee presence).
    """

    for b in builds:
        if getattr(b, "id", None) == build_id:
            return b
    raise AssertionError(f"build id not found: {build_id}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_catalog_has_components(catalog) -> None:
    """Ensure the catalog exposes at least the 8 base components."""

    assert len(catalog.items_components) >= 8
    assert len(catalog.champions) > 0


@pytest.mark.parametrize("build_id", ["double_trouble_fan_service", "sniper_squad"])  # type: ignore[misc]
def test_builds_load_ok(builds, build_id: str) -> None:
    """Ensure example builds can be loaded and looked up by id."""

    b = _get_build(builds, build_id)
    assert b.id == build_id
    assert b.name


def test_sniper_outranks_double_trouble_given_setup(
    builds, recipes, inventory_factory
) -> None:
    """Validate that, for a specific mid-game setup, Sniper Squad ranks higher.

    Setup rationale:
    - **Stage**: 3-2 (mid bucket dominates champion presence weight).
    - **Champions**: Gnar, Kennen, Malphite, Sivir (align with Sniper's early/mid comps).
    - **Components**: Chain Vest, Negatron Cloak, Tear, Giant's Belt (align with Sniper's priority).
    - **Augments**: none (notes-only; score unaffected).
    """

    sniper = _get_build(builds, "sniper_squad")
    dt = _get_build(builds, "double_trouble_fan_service")

    inv = inventory_factory(
        units={"Gnar": 1, "Kennen": 1, "Malphite": 1, "Sivir": 1},
        components={
            "Chain Vest": 1,
            "Negatron Cloak": 1,
            "Tear of the Goddess": 1,
            "Giant's Belt": 1,
        },
        augments=[],
        stage="3-2",
    )

    s_sniper: ScoreBreakdown = score_build(sniper, inv, recipes=recipes)
    s_dt: ScoreBreakdown = score_build(dt, inv, recipes=recipes)

    assert s_sniper.total > s_dt.total, (
        f"expected Sniper Squad to outrank Double Trouble — got {s_sniper.total:.3f} vs {s_dt.total:.3f}"
    )


def test_double_trouble_critical_note_triggers_without_augments(builds, inventory_factory) -> None:
    """Ensure the critical pivot note fires at stage ≥ 3-2 if Double Trouble is missing."""

    dt = _get_build(builds, "double_trouble_fan_service")
    inv = inventory_factory(
        units={},
        components={"Recurve Bow": 1},  # irrelevant; trigger is augment+stage
        augments=[],  # missing Double Trouble II/III
        stage="3-2",
    )

    msgs = evaluate_notes(dt, inv)
    severities = {m.severity.value for m in msgs}
    pivots = {m.pivot_to for m in msgs if m.pivot_to is not None}

    assert "critical" in severities, "expected a critical note to be emitted"
    assert "sniper_squad" in pivots, "expected a pivot suggestion to sniper_squad"


def test_assignment_coverage_is_exposed_in_score_details(builds, recipes, inventory_factory) -> None:
    """Check that assignment coverage appears in the score details for UI use.

    For Double Trouble priority [Bow, Rod, Bow, Negatron, Belt, BF] and inventory
    with one Bow and one Negatron, matched should be 2 of 6 (≈33%).
    """

    dt = _get_build(builds, "double_trouble_fan_service")
    inv = inventory_factory(
        units={},
        components={"Recurve Bow": 1, "Negatron Cloak": 1},
        augments=[],
        stage="3-2",
    )
    score = score_build(dt, inv, recipes=recipes)

    assignment = score.details.get("assignment")
    assert assignment is not None, "assignment details should be present"
    assert assignment.total == 6
    assert assignment.matched == 2
    assert pytest.approx(assignment.coverage, rel=1e-3) == 2 / 6