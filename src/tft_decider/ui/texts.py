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
    "TITLE_TOP_BUILDS",
    "TITLE_FORCED_BUILD",
    "TITLE_DETAILS",
    "TITLE_LINKS",
    "TITLE_NOTES",
    # Buttons / actions
    "BTN_FORCE",
    "BTN_OPEN_GUIDE",
    "BTN_OPEN_VIDEO",
    # Banners & misc
    "SEVERITY_EMOJI",
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

TITLE_TOP_BUILDS: Final[str] = "Top builds for your setup"
TITLE_FORCED_BUILD: Final[str] = "Forced build"
TITLE_DETAILS: Final[str] = "Details"
TITLE_LINKS: Final[str] = "Links"
TITLE_NOTES: Final[str] = "Notes & banners"

# ---------------------------------------------------------------------------
# Buttons / actions
# ---------------------------------------------------------------------------
BTN_FORCE: Final[str] = "Force"
BTN_OPEN_GUIDE: Final[str] = "Open guide"
BTN_OPEN_VIDEO: Final[str] = "Open video"

# ---------------------------------------------------------------------------
# Banners & icons
# ---------------------------------------------------------------------------
SEVERITY_EMOJI: Final[dict[str, str]] = {
    "info": "ℹ️",
    "warning": "⚠️",
    "critical": "🛑",
}


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