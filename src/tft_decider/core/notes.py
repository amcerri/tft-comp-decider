"""
Notes and banners evaluation engine.

Overview
--------
Evaluate build notes with triggers and return banner-like messages for the UI.
Triggers are simple, explainable predicates (e.g., missing augments, having any
component, minimum stage). Notes do **not** affect the numeric score; they
provide actionable guidance (info/warning/critical) and may suggest a pivot.

Design
------
- Keep the logic deterministic and transparent; avoid hidden globals.
- Depend only on previously defined internal modules (types/models/logging).
- Provide small data containers for UI consumption with explicit severities.

Integration
-----------
Called by the UI after scoring to render banners and potential pivot links.
This module has no side effects besides structured logging.

Usage
-----
>>> from tft_decider.core.models import Inventory
>>> from tft_decider.data.data_loader import load_build_from_yaml
>>> from tft_decider.core.notes import evaluate_notes
>>> inv = Inventory(units={}, items_components={"Recurve Bow": 1}, augments=[], stage="3-2")
>>> b = load_build_from_yaml("data/builds/double_trouble_fan_service.yaml")
>>> msgs = evaluate_notes(b, inv)
>>> any(m.severity.value == "critical" for m in msgs)
True
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Optional

from tft_decider.core.models import Build, Inventory, Note
from tft_decider.core.types import BuildId, Severity, stage_ge
from tft_decider.infra.logging import generate_thread_id, logger_for

__all__: Final[list[str]] = [
    "EvaluatedNote",
    "evaluate_notes",
    "most_severe",
    "has_critical",
]


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class EvaluatedNote:
    """Represent a note ready for display in the UI.

    Attributes:
        severity: One of :class:`Severity` (info, warning, critical).
        text: Human-readable message (English-only as per project rules).
        pivot_to: Optional build id to suggest as a pivot.
        details: Optional diagnostics about which triggers fired.
    """

    severity: Severity
    text: str
    pivot_to: Optional[BuildId]
    details: dict[str, Any]


# ---------------------------------------------------------------------------
# Core evaluation logic
# ---------------------------------------------------------------------------

def _evaluate_single(note: Note, inv: Inventory) -> tuple[bool, dict[str, Any]]:
    """Evaluate a single note's triggers against the inventory.

    The logic is an **AND** over active trigger fields: when a field is present
    in the note, it must pass for the note to fire. Individual fields may use
    "any" semantics as specified by the schema (e.g., ``missing_augments_any``).

    Args:
        note: The note definition with triggers.
        inv: The current inventory/state.

    Returns:
        A pair ``(ok, details)`` where ``ok`` indicates whether the note fired,
        and ``details`` contains diagnostics (useful for the UI and logs).
    """

    t = note.triggers
    have_aug = set(inv.augments)
    comps = inv.items_components

    details: dict[str, Any] = {
        "missing_augments_any": None,
        "have_components_any": None,
        "stage_min": None,
    }

    ok = True

    # missing_augments_any → true if at least one listed augment is missing
    if t.missing_augments_any:
        missing = [a for a in t.missing_augments_any if a not in have_aug]
        details["missing_augments_any"] = missing
        ok &= len(missing) > 0

    # have_components_any → true if at least one listed component is present (>0)
    if t.have_components_any:
        have_any = [c for c in t.have_components_any if comps.get(c, 0) > 0]
        details["have_components_any"] = have_any
        ok &= len(have_any) > 0

    # stage_min → require inv.stage >= stage_min
    if t.stage_min:
        stage_ok = stage_ge(inv.stage, t.stage_min)
        details["stage_min"] = {"required": t.stage_min, "have": inv.stage, "ok": stage_ok}
        ok &= stage_ok

    return ok, details


def evaluate_notes(build: Build, inv: Inventory, *, thread_id: Optional[str] = None) -> list[EvaluatedNote]:
    """Evaluate all notes for a build and return banner-friendly messages.

    Args:
        build: The build whose notes will be evaluated.
        inv: The current inventory/state.
        thread_id: Optional correlation ID for structured logging.

    Returns:
        A list of :class:`EvaluatedNote` entries (possibly empty).
    """

    log = logger_for(component="core.notes", event="evaluate", thread_id=thread_id or generate_thread_id())

    results: list[EvaluatedNote] = []
    for n in build.notes:
        ok, details = _evaluate_single(n, inv)
        if ok:
            results.append(
                EvaluatedNote(
                    severity=n.severity,
                    text=n.text,
                    pivot_to=n.triggers.suggest_pivot_to,
                    details=details,
                )
            )

    # Logging summary with severity counters
    counts = {k: 0 for k in (Severity.INFO, Severity.WARNING, Severity.CRITICAL)}
    for m in results:
        counts[m.severity] += 1
    log.info(
        "Notes evaluated",
        build_id=build.id,
        info=counts[Severity.INFO],
        warning=counts[Severity.WARNING],
        critical=counts[Severity.CRITICAL],
        total=len(results),
    )

    return results


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def most_severe(messages: list[EvaluatedNote]) -> Optional[Severity]:
    """Return the highest severity present in ``messages`` or ``None`` if empty."""

    order = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}
    if not messages:
        return None
    return max((m.severity for m in messages), key=lambda s: order[s])


def has_critical(messages: list[EvaluatedNote]) -> bool:
    """Return whether there is any ``critical`` message in ``messages``."""

    return any(m.severity is Severity.CRITICAL for m in messages)