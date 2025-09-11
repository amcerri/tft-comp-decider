"""
Reusable Streamlit widgets for the UI.

Overview
--------
Provide small, stateless helpers to render interactive controls used across the
app, such as a component counter grid (click to +1) and an owned-item list with
quick decrement (click to −1). These helpers encapsulate Streamlit event wiring
and state handling via ``st.session_state``. It also includes presentational
helpers to render “pills” (tags) and colored coverage (have/missing).

Design
------
- Keep functions focused and side-effect free except for ``st.session_state``.
- Do not import project internals other than Streamlit; callers pass labels.
- Use deterministic Streamlit keys so widgets do not clash across reruns.
- CSS for colored pills is injected on every rerun for robustness.

Integration
-----------
Imported by ``ui/app.py`` to render the component selection UX and build cards.
The functions return updated state mappings so callers can consume them.

Usage
-----
>>> import streamlit as st
>>> from tft_decider.ui.widgets import (
...     render_component_counter_grid, render_owned_counters,
...     render_diff_pills, ensure_pill_css_once,
... )
>>> state = render_component_counter_grid(["Recurve Bow", "Chain Vest"], state_key="components")
>>> render_owned_counters(state_key="components")
>>> ensure_pill_css_once()
>>> render_diff_pills("Final comp", ["Xayah", "Rakan"], present={"Xayah"})
"""

from __future__ import annotations

from typing import Final, Iterable, Optional, Sequence, Set

import streamlit as st

__all__: Final[list[str]] = [
    "ensure_session_counter_map",
    "render_component_counter_grid",
    "render_owned_counters",
    "render_champion_pills",
    "render_item_priority",
    "render_string_pills",
    "ensure_pill_css_once",
    "render_diff_pills",
    "heat_colors",
    "render_heat_strip",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def ensure_session_counter_map(state_key: str) -> dict[str, int]:
    """Ensure a dict[str, int] exists in session_state and return it.

    Args:
        state_key: The key to use inside ``st.session_state``.

    Returns:
        The mutable mapping stored under ``state_key``.
    """
    if state_key not in st.session_state or not isinstance(st.session_state[state_key], dict):
        st.session_state[state_key] = {}
    # Coerce values to int defensively
    st.session_state[state_key] = {k: int(v) for k, v in st.session_state[state_key].items()}
    return st.session_state[state_key]


def _inc(map_obj: dict[str, int], name: str, delta: int = 1) -> None:
    """Increment a counter in-place; delete the key if it drops to <= 0."""
    new_val = int(map_obj.get(name, 0)) + int(delta)
    if new_val <= 0:
        map_obj.pop(name, None)
    else:
        map_obj[name] = new_val


# ---------------------------------------------------------------------------
# Public widgets
# ---------------------------------------------------------------------------

def render_component_counter_grid(
    components: Iterable[str],
    *,
    state_key: str = "components",
    columns: int = 2,
    inc_label: str = "+",
    help_text: Optional[str] = None,
    key_namespace: Optional[str] = None,
) -> dict[str, int]:
    """Render a grid of buttons where each click increments a component by +1.

    Args:
        components: The iterable of component names to render.
        state_key: The ``st.session_state`` key where the counters are stored.
        columns: Number of columns in the grid (>= 1).
        inc_label: Label prefix for the increment buttons (e.g., "+").
        help_text: Optional tooltip/help shown above the grid.
        key_namespace: Optional prefix to ensure unique widget keys across multiple renderings.

    Returns:
        The updated mapping ``dict[name -> count]`` from ``st.session_state``.
    """
    counter_map = ensure_session_counter_map(state_key)

    if help_text:
        st.caption(help_text)

    prefix = f"{key_namespace}::" if key_namespace else ""

    cols = st.columns(max(1, int(columns)))
    for i, name in enumerate(components):
        col = cols[i % len(cols)]
        with col:
            key = f"{prefix}inc::{state_key}::{name}"
            if st.button(f"{inc_label} {name}", key=key, use_container_width=True):
                _inc(counter_map, name, +1)
                try:
                    st.rerun()
                except AttributeError:
                    # Fallback for older Streamlit versions
                    pass
    return counter_map


def render_owned_counters(
    *,
    state_key: str = "components",
    title: Optional[str] = None,
    dec_label: str = "−",
    columns: int = 3,
    key_namespace: Optional[str] = None,
) -> dict[str, int]:
    """Render the list of owned items with a quick decrement button per entry.

    Args:
        state_key: The ``st.session_state`` key where the counters are stored.
        title: Optional title to display above the list.
        dec_label: Label prefix for the decrement buttons (e.g., "−").
        columns: Number of columns for the decrement grid (>= 1).
        key_namespace: Optional prefix to ensure unique widget keys across multiple renderings.

    Returns:
        The updated mapping ``dict[name -> count]`` from ``st.session_state``.
    """
    counter_map = ensure_session_counter_map(state_key)

    if title:
        st.subheader(title)

    if not counter_map:
        st.caption("No items selected yet.")
        return counter_map

    prefix = f"{key_namespace}::" if key_namespace else ""

    # Display as a responsive grid of decrement buttons with counts
    items = sorted(counter_map.items(), key=lambda kv: kv[0].lower())
    cols = st.columns(max(1, int(columns)))
    for i, (name, count) in enumerate(items):
        col = cols[i % len(cols)]
        with col:
            key = f"{prefix}dec::{state_key}::{name}"
            label = f"{dec_label} {name} (x{int(count)})"
            if st.button(label, key=key, use_container_width=True):
                _inc(counter_map, name, -1)
                try:
                    st.rerun()
                except AttributeError:
                    # Fallback for older Streamlit versions
                    pass

    return counter_map


# ---------------------------------------------------------------------------
# Presentation helpers (stateless render)
# ---------------------------------------------------------------------------

def render_champion_pills(
    title: str,
    names: Sequence[str] | Iterable[str],
    *,
    core: Optional[Set[str]] = None,
    columns: int = 4,
) -> None:
    """Render a titled list of champion names as tag-like pills.

    Args:
        title: Section title to display above the pills.
        names: Champion names to render.
        core: Optional set of names to highlight as core (prefixed with a star).
        columns: Number of columns to distribute the pills across (>= 1).
    """
    core = set(core or set())
    names_list = [str(n) for n in names]

    st.subheader(title)
    if not names_list:
        st.caption("No entries.")
        return

    cols = st.columns(max(1, int(columns)))
    for i, name in enumerate(names_list):
        label = f"★ {name}" if name in core else name
        pill = f"`{label}`"  # inline code style for a simple pill look
        with cols[i % len(cols)]:
            st.markdown(pill)


def render_item_priority(title: str, items: Sequence[str] | Iterable[str]) -> None:
    """Render an ordered list of item components as the build's priority.

    Args:
        title: Section title to display above the list.
        items: Ordered item names (highest priority first).
    """
    items_list = [str(x) for x in items]

    st.subheader(title)
    if not items_list:
        st.caption("No items specified.")
        return

    md = "\n".join(f"{i}. {x}" for i, x in enumerate(items_list, start=1))
    st.markdown(md)


def render_string_pills(title: str, items: Sequence[str] | Iterable[str], *, columns: int = 6) -> None:
    """Render a titled list of generic strings as tag-like pills.

    Args:
        title: Section title to display above the pills.
        items: The strings to render as pills.
        columns: Number of columns to distribute the pills across (>= 1).
    """
    items_list = [str(x) for x in items]

    st.subheader(title)
    if not items_list:
        st.caption("No entries.")
        return

    cols = st.columns(max(1, int(columns)))
    for i, text in enumerate(items_list):
        pill = f"`{text}`"
        with cols[i % len(cols)]:
            st.markdown(pill)


# ---------------------------------------------------------------------------
# Colored pill rendering (have/missing) with per-rerun CSS
# ---------------------------------------------------------------------------

def ensure_pill_css_once() -> None:
    """Inject CSS for pill rendering on every rerun.

    Streamlit rebuilds the DOM on reruns; injecting the stylesheet each time
    guarantees classes like `.pill.ok` and `.pill.miss` stay styled.
    """
    css = """
    <style>
    .pill { display:inline-block; padding:0.15rem 0.55rem; border-radius:9999px;
            margin:0.15rem 0.35rem 0 0; font-size:0.9rem; line-height:1.4;
            border:1px solid rgba(0,0,0,0.1); }
    .pill.ok { background: rgba(16,185,129,0.15); border-color: rgba(16,185,129,0.35); }
    .pill.miss { background: rgba(239,68,68,0.15); border-color: rgba(239,68,68,0.35); }
    .pill.core { font-weight:600; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def render_diff_pills(
    title: str,
    targets: Sequence[str] | Iterable[str],
    present: Set[str] | set[str],
    *,
    columns: int = 6,
    mark_core: Optional[Set[str]] = None,
    boxed: bool = True,
) -> None:
    """Render a titled box of colored pills contrasting targets vs. present.

    Args:
        title: Section title to display.
        targets: Ordered names we want to show (e.g., comp units or components).
        present: Set of names considered "owned"/"included" (rendered green).
        columns: Number of columns to distribute the pills across (>= 1).
        mark_core: Optional set of names to highlight as core.
        boxed: Whether to wrap the section in a bordered container.
    """
    ensure_pill_css_once()

    names = [str(t) for t in targets]
    core = set(mark_core or set())

    def _render(names_list: list[str]) -> None:
        st.subheader(title)
        if not names_list:
            st.caption("No entries.")
            return
        cols = st.columns(max(1, int(columns)))
        for i, name in enumerate(names_list):
            is_ok = name in present
            is_core = name in core
            classes = ["pill", "ok" if is_ok else "miss"]
            if is_core:
                classes.append("core")
            label = f"★ {name}" if is_core else name
            html = f"<span class='{' '.join(classes)}'>{label}</span>"
            with cols[i % len(cols)]:
                st.markdown(html, unsafe_allow_html=True)

    if boxed:
        with st.container(border=True):
            _render(names)
    else:
        _render(names)


# ---------------------------------------------------------------------------
# Heat helpers for champion selectors
# ---------------------------------------------------------------------------

def heat_colors(score: float) -> tuple[str, str]:
    """Return (background_rgba, border_rgba) for a heat score in [0, 1].

    Uses a red→yellow→green gradient with gamma adjustment to increase
    mid-range contrast. ``score=0.0`` renders red, ``~0.5`` renders yellow,
    and ``1.0`` renders green. Input is clamped to [0, 1].
    """
    # Clamp and apply gamma to emphasize mid-range values
    s = max(0.0, min(1.0, float(score)))
    s_adj = s ** 0.7  # gamma < 1 brightens medium scores

    # RGB anchors
    red = (239, 68, 68)
    yellow = (234, 179, 8)
    green = (16, 185, 129)

    # Piecewise linear blend: red→yellow (0..0.5), yellow→green (0.5..1)
    if s_adj <= 0.5:
        t = 0.0 if s_adj <= 0.0 else (s_adj / 0.5)
        r = int(red[0] + t * (yellow[0] - red[0]))
        g = int(red[1] + t * (yellow[1] - red[1]))
        b = int(red[2] + t * (yellow[2] - red[2]))
    else:
        t = (s_adj - 0.5) / 0.5
        r = int(yellow[0] + t * (green[0] - yellow[0]))
        g = int(yellow[1] + t * (green[1] - yellow[1]))
        b = int(yellow[2] + t * (green[2] - yellow[2]))

    # Opacity scales with adjusted score for both bg and border
    bg_alpha = 0.20 + 0.35 * s_adj   # 0.20 → 0.55
    border_alpha = 0.35 + 0.30 * s_adj  # 0.35 → 0.65

    bg = f"rgba({r},{g},{b},{bg_alpha:.3f})"
    border = f"rgba({r},{g},{b},{border_alpha:.3f})"
    return (bg, border)


def render_heat_strip(score: float, *, height: int = 8, margin_bottom: int = 6) -> None:
    """Render a thin colored strip representing the heat score.

    Args:
        score: Heat value in [0, 1]. 0.0 renders a soft red; >0 renders green.
        height: Height of the strip in CSS pixels.
        margin_bottom: Bottom margin in CSS pixels.
    """
    bg, border = heat_colors(score)
    st.markdown(
        (
            f"<div style=\"height:{int(height)}px; background:{bg}; "
            f"border:1px solid {border}; border-radius:9999px; "
            f"margin-bottom:{int(margin_bottom)}px;\"></div>"
        ),
        unsafe_allow_html=True,
    )