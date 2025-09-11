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

from tft_decider.core.analytics import compute_champion_heat

from tft_decider.infra.logging import setup_logging, logger_for, generate_thread_id
from tft_decider.data.catalog import (
    Catalog,
    load_catalog_from_yaml,
    available_champions,
    available_components,
    available_augments,
    available_costs,
    available_champion_traits,
)
from tft_decider.data.data_loader import load_builds_from_dir
from tft_decider.core.models import Build, Inventory
from tft_decider.core.scoring import ScoreBreakdown, score_build
from tft_decider.core.notes import evaluate_notes, EvaluatedNote
from tft_decider.ui import texts
from tft_decider.ui.widgets import (
    render_component_counter_grid,
    render_owned_counters,
    render_diff_pills,
    ensure_pill_css_once,
    render_heat_strip,
)

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

        # Build details (comps and item priority)
        with st.expander(texts.TITLE_BUILD_DETAILS, expanded=True):
            # # Legend (have/missing) and CSS
            # try:
            #     ensure_pill_css_once()
            #     st.markdown(
            #         (
            #             f"<div style='margin-bottom:0.25rem'>"
            #             f"<strong>{texts.SECTION_LEGEND}:</strong> "
            #             f"<span class='pill ok'>{texts.LEGEND_HAVE}</span> "
            #             f"<span class='pill miss'>{texts.LEGEND_MISSING}</span>"
            #             f"</div>"
            #         ),
            #         unsafe_allow_html=True,
            #     )
            # except Exception:
            #     pass

            # Determine present sets
            owned_champs = set(getattr(inv, "units", {}).keys()) if "inv" in globals() else set()
            inc_components = set(getattr(assignment, "included_components", []) or []) if assignment is not None else set()
            have_components = set(getattr(inv, "items_components", {}).keys()) if "inv" in globals() else set()
            core_raw = (getattr(build, "core_units", []) or [])
            core_set = {getattr(c, "name", str(c)) for c in core_raw}

            # Early comp as colored diff pills (if provided)
            if getattr(build, "early_comp", None):
                try:
                    render_diff_pills(
                        texts.LABEL_EARLY_COMP,
                        build.early_comp,
                        present=owned_champs,
                        mark_core=core_set,
                        columns=6,
                        boxed=True,
                    )
                except Exception:
                    pass

            # Mid comp as colored diff pills (if provided)
            if getattr(build, "mid_comp", None):
                try:
                    render_diff_pills(
                        texts.LABEL_MID_COMP,
                        build.mid_comp,
                        present=owned_champs,
                        mark_core=core_set,
                        columns=6,
                        boxed=True,
                    )
                except Exception:
                    pass


            # Full/Late comp as colored diff pills (if provided)
            late_comp = getattr(build, "late_comp", None)
            if late_comp:
                try:
                    render_diff_pills(
                        texts.LABEL_FULL_COMP,
                        late_comp,
                        present=owned_champs,
                        mark_core=core_set,
                        columns=6,
                        boxed=True,
                    )
                except Exception:
                    pass

            # Final comp (only if no explicit late/full comp provided)
            if not late_comp:
                try:
                    render_diff_pills(
                        texts.LABEL_FINAL_COMP,
                        build.comp,
                        present=owned_champs,
                        mark_core=core_set,
                        columns=10,
                        boxed=True,
                    )
                except Exception:
                    pass

            # Components coverage against priority list (fallback if missing)
            try:
                # Present set: what the user actually owns in inventory
                have_components = set(getattr(inv, "items_components", {}).keys()) if "inv" in globals() else set()

                # Targets: prefer item_priority from the build; if empty, fallback
                # to the union of included + missing from assignment to at least
                # show something meaningful to the user.
                targets_components = list(getattr(build, "item_priority", []) or [])
                if not targets_components and assignment is not None:
                    inc_list = list(getattr(assignment, "included_components", []) or [])
                    miss_list = list(getattr(assignment, "missing_components", []) or [])
                    # Preserve order: included first, then any missing not already listed
                    seen: set[str] = set()
                    targets_components = []
                    for n in inc_list + miss_list:
                        if n not in seen:
                            targets_components.append(n)
                            seen.add(n)

                if targets_components:
                    render_diff_pills(
                        texts.SECTION_COMPONENTS_COVERAGE,
                        targets_components,
                        present=have_components,
                        columns=6,
                        boxed=True,
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
# Champions & components selectors (new UX)
# ---------------------------------------------------------------------------

def _render_champions_selector(catalog: Catalog, champ_heat: dict[str, float] | None = None) -> dict[str, int]:
    """Render champions selector in the sidebar.

    When ``champions_index`` is available, show **cost/trait filters** and a
    **grid per cost** with several champions per row (checkboxes). Otherwise,
    fall back to a simple multiselect.

    Returns:
        A mapping ``name -> 1`` representing owned champions (1★ assumed).
    """

    st.sidebar.subheader(texts.SECTION_CHAMPIONS)

    # Current state
    if "units" not in st.session_state or not isinstance(st.session_state["units"], dict):
        st.session_state["units"] = {}
    state_units: dict[str, int] = {k: int(v) for k, v in st.session_state["units"].items()}

    # Canonical path: champions_index exists → filters + grid
    if catalog.champions_index:
        with st.sidebar.expander(texts.SECTION_FILTERS, expanded=True):
            costs = available_costs(catalog)
            traits = available_champion_traits(catalog)
            selected_costs = st.multiselect(texts.FILTER_COSTS, options=costs, default=costs)
            selected_traits = st.multiselect(texts.FILTER_TRAITS, options=traits)
            st.sidebar.caption(texts.HINT_CHAMPIONS_ADD_ONLY)

        # Build filtered groups by cost
        groups: dict[int, list[str]] = {}
        for c in catalog.champions_index:
            if selected_costs and c.cost not in selected_costs:
                continue
            if selected_traits and not any(t in c.traits for t in selected_traits):
                continue
            groups.setdefault(c.cost, []).append(c.name)

        for cost in sorted(groups.keys()):
            names = sorted(groups[cost], key=str.lower)
            st.sidebar.markdown(f"**{cost} Cost**")
            cols = st.sidebar.columns(3)
            for i, name in enumerate(names):
                with cols[i % len(cols)]:
                    # Heat-based colored strip (green intensity by relevance; red if unused)
                    score = 0.0 if champ_heat is None else float(champ_heat.get(name, 0.0))
                    render_heat_strip(score)

                    key = f"unit::add::{name}"
                    if st.button(name, key=key, use_container_width=True):
                        if name not in state_units:
                            state_units[name] = 1
                            st.session_state["units"] = state_units
                            try:
                                st.rerun()
                            except AttributeError:
                                pass

        st.session_state["units"] = state_units
        return dict(state_units)

    # Fallback: legacy simple list
    champs = available_champions(catalog)
    selected = st.sidebar.multiselect("Owned champions (1★ assumed)", options=champs)
    result = {name: 1 for name in selected}
    st.session_state["units"] = result
    return result


def _render_components_selector(catalog: Catalog) -> dict[str, int]:
    """Render components selector using click-to-add (+1) and owned list (−1)."""

    with st.sidebar:
        st.subheader(texts.SECTION_COMPONENTS)
        comps = available_components(catalog)
        render_component_counter_grid(
            comps,
            state_key="components",
            columns=2,
            inc_label=texts.BTN_INC,
            help_text=texts.HINT_CLICK_TO_ADD,
        )

    # Ensure a dict exists
    if "components" not in st.session_state or not isinstance(st.session_state["components"], dict):
        st.session_state["components"] = {}
    # Coerce to int
    st.session_state["components"] = {k: int(v) for k, v in st.session_state["components"].items() if int(v) > 0}
    return st.session_state["components"]


def _render_selection_summary(units_map: dict[str, int]) -> None:
    """Render a compact summary of the current selection in the main area.

    Champions are shown as removable chips; components are shown below using the
    shared owned-counters widget.
    """

    # st.header(texts.SECTION_SELECTION_SUMMARY)

    # Champions summary with remove buttons
    st.subheader(texts.SECTION_OWNED_CHAMPIONS)
    if not units_map:
        st.caption("No champions selected yet.")
    else:
        names = sorted([n for n, s in units_map.items() if int(s) > 0], key=str.lower)
        cols = st.columns(4)
        for i, name in enumerate(names):
            with cols[i % len(cols)]:
                if st.button(f"× {name}", key=f"rm-unit::{name}", use_container_width=True):
                    # Remove from session and trigger rerun
                    try:
                        st.session_state["units"].pop(name, None)
                        st.rerun()
                    except AttributeError:
                        # Older Streamlit versions: no immediate rerun
                        pass

    # Components summary (re-use the owned counters without a title)
    st.subheader(texts.SECTION_COMPONENTS_OWNED)
    render_owned_counters(state_key="components", title=None, dec_label=texts.BTN_DEC, columns=3)


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
    # Ensure pill CSS is present from the start of each rerun
    try:
        ensure_pill_css_once()
    except Exception:
        pass
    # Slightly widen the sidebar for denser controls
    st.markdown(
        "<style>[data-testid='stSidebar'] {width: 360px;}</style>",
        unsafe_allow_html=True,
    )

    # Inform when using a custom data directory via environment variable
    # Only enable for debugging. Hidden by default.
    # if os.environ.get("TFT_DATA_DIR"):
    #     st.info(f"Using data directory from TFT_DATA_DIR: `{DATA_DIR}`")

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
        champ_heat = compute_champion_heat(builds)
    except Exception as exc:
        st.error(f"Failed to load builds directory: {BUILDS_DIR}")
        log.error("Builds load failure (UI)", error=str(exc))
        return

    if not builds:
        st.warning(f"No builds found under: {BUILDS_DIR}")
        return

    # Sidebar — Inventory selections
    st.sidebar.header(texts.SECTION_INVENTORY)

    # Run options (collapsed by default): Stage & Augments
    with st.sidebar.expander(texts.RUN_OPTIONS, expanded=False):
        st.subheader(texts.SECTION_STAGE)
        stage = st.selectbox(
            "Pick your current stage",
            options=["2-1", "2-5", "3-2", "4-1", "4-5", "5-1"],
            index=["2-1", "2-5", "3-2", "4-1", "4-5", "5-1"].index(DEFAULT_STAGE),
        )

        st.subheader(texts.SECTION_AUGMENTS)
        augs = available_augments(catalog)
        selected_augments = st.multiselect("Owned augments (notes only)", options=augs)

    # Components selection — click-to-add + owned list (replaces numeric inputs)
    component_counts = _render_components_selector(catalog)

    # Forced build
    st.sidebar.subheader(texts.SECTION_FORCED_BUILD)
    force_on = st.sidebar.checkbox("Force a build", value=False)
    forced_id = None
    if force_on:
        ids = [b.id for b in builds]
        forced_id = st.sidebar.selectbox("Select build to force", options=ids)

    # Champions selector (sidebar grid-by-cost with filters; fallback to legacy)
    units_map = _render_champions_selector(catalog, champ_heat=champ_heat)

    # Build inventory and compute ranking
    global inv  # allow use inside render function blocks for simplicity
    selected_champions = [name for name, stars in units_map.items() if int(stars) > 0]
    inv = _inventory_from_inputs(selected_champions, component_counts, selected_augments, stage)

    scored = _score_all_builds(builds, inv, recipes=_recipes_from_catalog(catalog), thread_id=thread_id)

    # Selection summary (main area)
    _render_selection_summary(units_map)

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
