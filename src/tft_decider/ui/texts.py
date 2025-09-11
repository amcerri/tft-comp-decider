"""
UI text constants and small format helpers.

Overview
--------
Centralize all user-facing strings (English-only) and a few small formatting
helpers used by the Streamlit UI. Keeping strings in a single place makes the
UI consistent and simplifies future refactors.

Design
------
- No imports from project internals to keep this module standalone.
- Provide only **pure** helpers (no I/O, no logging, no Streamlit calls).
- Offer tiny formatting utilities for scores and banners without UI concerns.

Integration
-----------
Imported by the Streamlit app to render labels, titles, and explanations. This
module has no side effects and is safe to import at any time.

Usage
-----
>>> from tft_decider.ui import texts
>>> texts.APP_TITLE
'TFT Comp Decider'
>>> texts.format_score_summary(total=0.73, champions=0.60, items=0.30, prior=0.10)
'Score 0.730 · Champions 0.600 · Items 0.300 · Prior 0.100'
"""

from __future__ import annotations

from typing import Final

__all__: Final[list[str]] = [
    # Titles & sections
    "APP_TITLE",
    "SECTION_INVENTORY",
    "SECTION_STAGE",
    "SECTION_CHAMPIONS",
    "SECTION_COMPONENTS",
    "SECTION_AUGMENTS",
    "SECTION_FORCED_BUILD",
    "RUN_OPTIONS",
    "SECTION_FILTERS",
    "FILTER_COSTS",
    "FILTER_TRAITS",
    "SECTION_COMPONENTS_OWNED",
    "SECTION_SELECTION_SUMMARY",
    "SECTION_OWNED_CHAMPIONS",
    "TITLE_TOP_BUILDS",
    "TITLE_FORCED_BUILD",
    "TITLE_DETAILS",
    "TITLE_LINKS",
    "TITLE_NOTES",
    "TITLE_BUILD_DETAILS",
    "LABEL_CORE_UNITS",
    "LABEL_EARLY_COMP",
    "LABEL_MID_COMP",
    "LABEL_FINAL_COMP",
    "LABEL_FULL_COMP",
    "LABEL_ITEM_PRIORITY",
    "BADGE_CORE",
    "LABEL_COMPONENTS_INCLUDED",
    "LABEL_COMPONENTS_MISSING",
    "LABEL_COMPONENTS_LEFTOVER",
    "SECTION_LEGEND",
    "LEGEND_HAVE",
    "LEGEND_MISSING",
    "SECTION_COMPONENTS_COVERAGE",
    # Buttons / actions
    "BTN_FORCE",
    "BTN_OPEN_GUIDE",
    "BTN_OPEN_VIDEO",
    "BTN_INC",
    "BTN_DEC",
    # Banners & misc
    "SEVERITY_EMOJI",
    "HINT_CLICK_TO_ADD",
    "HINT_CHAMPIONS_ADD_ONLY",
    "format_score_summary",
    "format_assignment_summary",
    "format_percentage",
    "severity_badge",
]


# ---------------------------------------------------------------------------
# Titles & section labels
# ---------------------------------------------------------------------------
APP_TITLE: Final[str] = "TFT Comp Decider"

SECTION_INVENTORY: Final[str] = "Inventory"
SECTION_STAGE: Final[str] = "Stage"
SECTION_CHAMPIONS: Final[str] = "Champions"
SECTION_COMPONENTS: Final[str] = "Item components"
SECTION_AUGMENTS: Final[str] = "Augments (for notes only)"
SECTION_FORCED_BUILD: Final[str] = "Force build"
RUN_OPTIONS: Final[str] = "Run options"
SECTION_FILTERS: Final[str] = "Filters"
FILTER_COSTS: Final[str] = "Costs"
FILTER_TRAITS: Final[str] = "Traits"
SECTION_COMPONENTS_OWNED: Final[str] = "Owned components"
SECTION_SELECTION_SUMMARY: Final[str] = "Your selection"
SECTION_OWNED_CHAMPIONS: Final[str] = "Owned champions"

TITLE_TOP_BUILDS: Final[str] = "Top builds for your setup"
TITLE_FORCED_BUILD: Final[str] = "Forced build"
TITLE_DETAILS: Final[str] = "Details"
TITLE_LINKS: Final[str] = "Links"
TITLE_NOTES: Final[str] = "Notes & banners"
TITLE_BUILD_DETAILS: Final[str] = "Build details"
LABEL_CORE_UNITS: Final[str] = "Core units"
LABEL_EARLY_COMP: Final[str] = "Early comp"
LABEL_MID_COMP: Final[str] = "Mid comp"
LABEL_FINAL_COMP: Final[str] = "Final comp"
LABEL_FULL_COMP: Final[str] = "Full comp"
LABEL_ITEM_PRIORITY: Final[str] = "Item priority"
BADGE_CORE: Final[str] = "★ core"
LABEL_COMPONENTS_INCLUDED: Final[str] = "Included components"
LABEL_COMPONENTS_MISSING: Final[str] = "Missing components"
LABEL_COMPONENTS_LEFTOVER: Final[str] = "Leftover components"
SECTION_LEGEND: Final[str] = "Legend"
LEGEND_HAVE: Final[str] = "have"
LEGEND_MISSING: Final[str] = "missing"
SECTION_COMPONENTS_COVERAGE: Final[str] = "Components coverage"

# ---------------------------------------------------------------------------
# Buttons / actions
# ---------------------------------------------------------------------------
BTN_FORCE: Final[str] = "Force"
BTN_OPEN_GUIDE: Final[str] = "Open guide"
BTN_OPEN_VIDEO: Final[str] = "Open video"
BTN_INC: Final[str] = "+"
BTN_DEC: Final[str] = "−"

# ---------------------------------------------------------------------------
# Banners & icons
# ---------------------------------------------------------------------------
SEVERITY_EMOJI: Final[dict[str, str]] = {
    "info": "ℹ️",
    "warning": "⚠️",
    "critical": "🛑",
}


HINT_CLICK_TO_ADD: Final[str] = "Click to add +1; click an owned item to remove."
HINT_CHAMPIONS_ADD_ONLY: Final[str] = "Click to add; remove champions in the main summary."


# ---------------------------------------------------------------------------
# Formatting helpers (pure functions)
# ---------------------------------------------------------------------------

def format_percentage(value: float, *, digits: int = 1) -> str:
    """Format a float as a percentage string.

    Args:
        value: The numeric value in ``[0, 1]``.
        digits: Number of decimal digits.

    Returns:
        A percentage string like ``"63.2%"``.
    """

    pct = max(0.0, min(1.0, float(value))) * 100.0
    return f"{pct:.{digits}f}%"


def format_score_summary(*, total: float, champions: float, items: float, prior: float) -> str:
    """Return a compact textual summary of the score components.

    Args:
        total: Final score in ``[0, 1]``.
        champions: Champions score in ``[0, 1]``.
        items: Items score in ``[0, 1]``.
        prior: Prior score in ``[0, 1]``.

    Returns:
        A single-line summary suitable for UI display.
    """

    return (
        f"Score {total:.3f} · Champions {champions:.3f} · Items {items:.3f} · Prior {prior:.3f}"
    )


def format_assignment_summary(*, matched: int, total: int, coverage: float) -> str:
    """Return a compact summary of component assignment coverage.

    Args:
        matched: Number of priority slots covered.
        total: Total number of priority slots.
        coverage: Coverage ratio in ``[0, 1]``.

    Returns:
        A short string like ``"3/6 (50.0%)"``.
    """

    return f"{matched}/{max(total, 1)} ({format_percentage(coverage, digits=1)})"


def severity_badge(severity: str) -> str:
    """Return a small badge (emoji + uppercase label) for a severity string.

    Args:
        severity: One of ``"info"``, ``"warning"``, ``"critical"``.

    Returns:
        A badge string like ``"🛑 CRITICAL"``.
    """

    label = severity.upper()
    return f"{SEVERITY_EMOJI.get(severity, '')} {label}".strip()