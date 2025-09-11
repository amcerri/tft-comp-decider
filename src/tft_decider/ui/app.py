"""
Streamlit UI for the TFT Comp Decider.

Overview
--------
Provide a minimal, professional UI to:
- Load the local catalog (champions/components) and builds (YAML).
- Let users select owned champions, item components (with counts), augments, and stage.
- Optionally force a specific build to the top of the list.
- Compute scores for all builds and display the Top N with links and notes.

Design
------
- Keep this module focused on UI glue; business logic stays in core modules.
- Use structured logging (structlog) with mandatory fields: component, event, thread_id.
- Avoid external network calls; rely solely on local data files.

Integration
-----------
Run with:
    streamlit run src/tft_decider/ui/app.py
This file imports the previously defined loaders and engines.

Usage
-----
>>> # Run via Streamlit as shown above; not intended for direct import usage.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Final, Iterable

import streamlit as st

from tft_decider.infra.logging import setup_logging, logger_for, generate_thread_id
from tft_decider.data.catalog import (
    Catalog,
    load_catalog_from_yaml,
    available_champions,
    available_components,
    available_augments,
)
from tft_decider.data.data_loader import load_builds_from_dir
from tft_decider.core.models import Build, Inventory
from tft_decider.core.scoring import ScoreBreakdown, score_build
from tft_decider.core.notes import evaluate_notes, EvaluatedNote
from tft_decider.ui import texts

# UI configuration & constants
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR: Final[Path] = REPO_ROOT / "data"
DATA_DIR: Final[Path] = Path(os.environ.get("TFT_DATA_DIR", str(DEFAULT_DATA_DIR)))
CATALOG_PATH: Final[Path] = DATA_DIR / "catalog" / "15.4_en.yaml"
BUILDS_DIR: Final[Path] = DATA_DIR / "builds"
DEFAULT_STAGE: Final[str] = "3-2"
TOP_N_DEFAULT: Final[int] = 5


# ---------------------------------------------------------------------------
# Utilities (pure helpers)
# ---------------------------------------------------------------------------

def _recipes_from_catalog(catalog: Catalog) -> dict[str, list[str]]:
    """Build a mapping of completed item → components from the catalog.

    Args:
        catalog: The loaded catalog model.

    Returns:
        A dict mapping completed item names to their component list.
    """

    recipes: dict[str, list[str]] = {}
    for item in catalog.items_completed:
        recipes[item.name] = list(item.components)
    return recipes


def _inventory_from_inputs(
    selected_champions: Iterable[str],
    component_counts: dict[str, int],
    selected_augments: Iterable[str],
    stage: str,
) -> Inventory:
    """Construct an Inventory from UI selections.

    Champions are recorded with a default star level of 1 for simplicity.
    """

    units = {name: 1 for name in selected_champions}
    items_components = {k: int(v) for k, v in component_counts.items() if int(v) > 0}
    augments = list(selected_augments)
    return Inventory(units=units, items_components=items_components, augments=augments, stage=stage)


def _score_all_builds(
    builds: list[Build],
    inv: Inventory,
    *,
    recipes: dict[str, list[str]] | None,
    thread_id: str,
) -> list[tuple[ScoreBreakdown, Build]]:
    """Score all builds and return sorted pairs (score, build)."""

    log = logger_for(component="ui.app", event="rank", thread_id=thread_id)
    scored: list[tuple[ScoreBreakdown, Build]] = []
    for b in builds:
        s = score_build(b, inv, recipes=recipes, thread_id=thread_id)
        scored.append((s, b))
    scored.sort(key=lambda x: x[0].total, reverse=True)
    log.info("Builds ranked", total=len(scored))
    return scored


def _severity_to_st(severity: str):
    """Return the Streamlit banner function for a given severity string."""

    if severity == "critical":
        return st.error
    if severity == "warning":
        return st.warning
    return st.info


def _render_links(build: Build) -> None:
    """Render external links as buttons if present."""

    if not build.links:
        return
    cols = st.columns(min(3, len(build.links)))
    for i, link in enumerate(build.links):
        with cols[i % len(cols)]:
            try:
                st.link_button(link.label, link.url, use_container_width=True)
            except Exception:
                # Fallback for environments without link_button (older Streamlit)
                st.markdown(f"[{link.label}]({link.url})")


def _render_notes(messages: list[EvaluatedNote]) -> None:
    """Render evaluated notes as banners with emojis."""

    for m in messages:
        f = _severity_to_st(m.severity.value)
        f(f"{texts.severity_badge(m.severity.value)} {m.text}")
        if m.pivot_to:
            st.caption(f"Suggested pivot: **{m.pivot_to}**")


def _render_build_card(score: ScoreBreakdown, build: Build) -> None:
    """Render a single build card with score, links, and notes."""

    with st.container(border=True):
        st.subheader(f"{build.name} — Tier {build.tier} #{build.tier_rank} · Score {score.total:.3f}")

        # Score details summary
        st.caption(
            texts.format_score_summary(
                total=score.total,
                champions=score.champions,
                items=score.items,
                prior=score.prior,
            )
        )

        # Assignment summary if available
        assignment = score.details.get("assignment")
        if assignment is not None:
            try:
                st.caption(
                    "Components: "
                    + texts.format_assignment_summary(
                        matched=assignment.matched, total=assignment.total, coverage=assignment.coverage
                    )
                )
            except Exception:
                pass

        # Links
        if build.links:
            with st.expander(texts.TITLE_LINKS, expanded=False):
                _render_links(build)

        # Notes
        msgs = evaluate_notes(build, inv)
        if msgs:
            with st.expander(texts.TITLE_NOTES, expanded=True):
                _render_notes(msgs)


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

def run() -> None:
    """Run the Streamlit UI application."""

    setup_logging()
    thread_id = generate_thread_id()
    log = logger_for(component="ui.app", event="start", thread_id=thread_id)

    st.set_page_config(page_title=texts.APP_TITLE, layout="wide")
    st.title(texts.APP_TITLE)

    # Inform when using a custom data directory via environment variable
    if os.environ.get("TFT_DATA_DIR"):
        st.info(f"Using data directory from TFT_DATA_DIR: `{DATA_DIR}`")

    # Load catalog
    try:
        catalog = load_catalog_from_yaml(str(CATALOG_PATH), thread_id=thread_id)
        recipes = _recipes_from_catalog(catalog)
        log.info(
            "Catalog loaded in UI",
            champions=len(catalog.champions),
            components=len(catalog.items_components),
            recipes=len(recipes),
        )
    except Exception as exc:
        st.error(f"Failed to load catalog: {CATALOG_PATH}")
        log.error("Catalog load failure (UI)", error=str(exc))
        return

    # Load builds
    try:
        builds = load_builds_from_dir(str(BUILDS_DIR), thread_id=thread_id)
        log.info("Builds loaded in UI", count=len(builds))
    except Exception as exc:
        st.error(f"Failed to load builds directory: {BUILDS_DIR}")
        log.error("Builds load failure (UI)", error=str(exc))
        return

    if not builds:
        st.warning(f"No builds found under: {BUILDS_DIR}")
        return

    # Sidebar — Inventory selections
    st.sidebar.header(texts.SECTION_INVENTORY)

    # Stage selection
    st.sidebar.subheader(texts.SECTION_STAGE)
    stage = st.sidebar.selectbox(
        "Pick your current stage",
        options=["2-1", "2-5", "3-2", "4-1", "4-5", "5-1"],
        index=["2-1", "2-5", "3-2", "4-1", "4-5", "5-1"].index(DEFAULT_STAGE),
    )

    # Champions selection (multiselect has built-in search)
    st.sidebar.subheader(texts.SECTION_CHAMPIONS)
    champs = available_champions(catalog)
    selected_champions = st.sidebar.multiselect("Owned champions (1★ assumed)", options=champs)

    # Components selection — counts (8 base components → number inputs)
    st.sidebar.subheader(texts.SECTION_COMPONENTS)
    comps = available_components(catalog)
    component_counts: dict[str, int] = {}
    col_left, col_right = st.sidebar.columns(2)
    for i, comp in enumerate(comps):
        with (col_left if i % 2 == 0 else col_right):
            component_counts[comp] = int(st.number_input(comp, min_value=0, max_value=10, value=0, step=1))

    # Augments selection (for notes only)
    st.sidebar.subheader(texts.SECTION_AUGMENTS)
    augs = available_augments(catalog)
    selected_augments = st.sidebar.multiselect("Owned augments (notes only)", options=augs)

    # Forced build
    st.sidebar.subheader(texts.SECTION_FORCED_BUILD)
    force_on = st.sidebar.checkbox("Force a build", value=False)
    forced_id = None
    if force_on:
        ids = [b.id for b in builds]
        forced_id = st.sidebar.selectbox("Select build to force", options=ids)

    # Build inventory and compute ranking
    global inv  # allow use inside render function blocks for simplicity
    inv = _inventory_from_inputs(selected_champions, component_counts, selected_augments, stage)

    scored = _score_all_builds(builds, inv, recipes=_recipes_from_catalog(catalog), thread_id=thread_id)

    # Forced build card
    if force_on and forced_id:
        forced_pairs = [p for p in scored if p[1].id == forced_id]
        if forced_pairs:
            st.markdown(f"### ✅ {texts.TITLE_FORCED_BUILD}")
            _render_build_card(forced_pairs[0][0], forced_pairs[0][1])
            st.divider()

    # Top builds
    st.header(texts.TITLE_TOP_BUILDS)
    top_n = st.slider("How many builds to show?", min_value=1, max_value=min(10, len(scored)), value=TOP_N_DEFAULT)

    shown = 0
    for score, build in scored:
        if force_on and forced_id and build.id == forced_id:
            # Skip the forced build in the ranked list (already shown above)
            continue
        _render_build_card(score, build)
        shown += 1
        if shown >= top_n:
            break


# Run immediately when executed by Streamlit
run()
