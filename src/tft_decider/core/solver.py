"""
Item/component solver helpers.

Overview
--------
Provide small, deterministic helpers to:
- Assign owned **item components** against an ordered **priority list**.
- Estimate craftable **completed items** given component inventory and recipes.

These utilities are intentionally simple (greedy) and explainable. They can be
swapped later for more sophisticated solvers (e.g., Hungarian/ILP) without
changing the public API.

Design
------
- Keep this module self-contained (stdlib only + internal types/logging).
- Prefer immutable inputs and return small dataclasses as results.
- Greedy strategies are chosen for transparency and speed in the UI loop.

Integration
-----------
Used by the scoring engine to compute component coverage and by the UI to show
"what can I craft now?" hints. There are no side effects besides structured
logging when functions are called.

Usage
-----
>>> result = assign_components_by_priority(
...     priority=["Recurve Bow", "Needlessly Large Rod", "Recurve Bow"],
...     have={"Recurve Bow": 1, "Negatron Cloak": 1},
... )
>>> result.matched, result.total, round(result.coverage, 2)
(1, 3, 0.33)
>>> # Crafting feasibility (simplified):
>>> recipes = {"Guinsoo's Rageblade": ["Recurve Bow", "Needlessly Large Rod"]}
>>> craft = craftable_bis_items({"Xayah": ["Guinsoo's Rageblade"]}, recipes, {"Recurve Bow": 1, "Needlessly Large Rod": 1})
>>> craft.crafted
["Guinsoo's Rageblade"]
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Final, Iterable, Mapping, MutableMapping, Optional, Sequence

from tft_decider.core.types import ChampionName, ComponentName, CompletedItemName
from tft_decider.infra.logging import generate_thread_id, logger_for

__all__: Final[list[str]] = [
    "AssignmentResult",
    "assign_components_by_priority",
    "CraftResult",
    "craftable_bis_items",
    "missing_components_for_item",
]


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class AssignmentResult:
    """Hold results for component-to-priority assignment.

    Attributes:
        matched: Number of priority positions satisfied by owned components.
        total: Total number of priority positions considered.
        matches: Pairs of ``(index, component_name)`` matched in order.
        missing: Priority components that could not be satisfied (in order).
        remaining: Remaining components after assignment.
    """

    matched: int
    total: int
    matches: list[tuple[int, ComponentName]]
    missing: list[ComponentName]
    remaining: dict[ComponentName, int]

    @property
    def coverage(self) -> float:
        """Return coverage ratio ``matched / max(total, 1)``.

        Returns:
            The fraction of covered positions as a float in ``[0, 1]``.
        """

        return self.matched / max(self.total, 1)


@dataclass(slots=True)
class CraftResult:
    """Hold results for greedy crafting of completed items.

    Attributes:
        crafted: Completed item names crafted in the attempted order.
        crafted_per_carry: Mapping from carry → crafted items (attempt order).
        remaining_components: Components left after greedy crafting.
    """

    crafted: list[CompletedItemName]
    crafted_per_carry: dict[ChampionName, list[CompletedItemName]]
    remaining_components: dict[ComponentName, int]


# ---------------------------------------------------------------------------
# Core algorithms
# ---------------------------------------------------------------------------

def assign_components_by_priority(
    priority: Sequence[ComponentName],
    have: Mapping[ComponentName, int],
    *,
    thread_id: Optional[str] = None,
) -> AssignmentResult:
    """Assign components against an ordered priority list using a greedy strategy.

    The algorithm walks the priority list from left to right and, when a
    component is available, consumes one unit from the inventory and records the
    match. This is deterministic and easy to explain in the UI.

    Args:
        priority: Ordered list of desired components (most important first).
        have: Mapping of owned components to counts.
        thread_id: Optional correlation ID for structured logging.

    Returns:
        An :class:`AssignmentResult` with coverage details and remaining stock.
    """

    log = logger_for(component="core.solver", event="assign_priority", thread_id=thread_id or generate_thread_id())
    stock = Counter({k: int(v) for k, v in have.items() if int(v) > 0})
    matches: list[tuple[int, ComponentName]] = []
    missing: list[ComponentName] = []

    for idx, need in enumerate(priority):
        if stock.get(need, 0) > 0:
            stock[need] -= 1
            matches.append((idx, need))
        else:
            missing.append(need)

    # Remove zeroed entries to keep the result clean for UI display.
    remaining = {k: c for k, c in stock.items() if c > 0}

    result = AssignmentResult(
        matched=len(matches),
        total=len(priority),
        matches=matches,
        missing=missing,
        remaining=remaining,
    )
    log.info(
        "Component assignment computed",
        matched=result.matched,
        total=result.total,
        coverage=round(result.coverage, 3),
        missing=len(result.missing),
        unique_remaining=len(result.remaining),
    )
    return result


def missing_components_for_item(
    recipe: Sequence[ComponentName],
    stock: Mapping[ComponentName, int],
) -> dict[ComponentName, int]:
    """Return the missing components to craft a single completed item.

    Args:
        recipe: The list of components that form the item.
        stock: Current component inventory.

    Returns:
        A mapping of component → missing count (empty if fully craftable).
    """

    missing: Counter[ComponentName] = Counter()
    avail = Counter({k: int(v) for k, v in stock.items() if int(v) > 0})
    need = Counter([c for c in recipe if c])
    for comp, req in need.items():
        gap = req - avail.get(comp, 0)
        if gap > 0:
            missing[comp] = gap
    return dict(missing)


def craftable_bis_items(
    bis_by_carry: Mapping[ChampionName, Sequence[CompletedItemName]],
    recipes: Mapping[CompletedItemName, Sequence[ComponentName]],
    components: Mapping[ComponentName, int],
    *,
    per_carry_limit: Optional[int] = None,
    thread_id: Optional[str] = None,
) -> CraftResult:
    """Greedily craft completed items in the given per-carry order.

    The function iterates carries (in mapping order), then their desired items
    in order. If all components for an item are available, it is crafted and the
    components are consumed from the local stock. This is intentionally greedy
    and deterministic to keep the UI explanation simple.

    Args:
        bis_by_carry: Mapping of carry → desired completed items (ordered).
        recipes: Mapping from completed item name to its component recipe.
        components: Current component inventory (counts).
        per_carry_limit: Optional maximum number of items to craft per carry.
        thread_id: Optional correlation ID for logs.

    Returns:
        A :class:`CraftResult` listing crafted items, crafted-per-carry, and
        remaining components after the greedy pass.
    """

    log = logger_for(component="core.solver", event="craft_bis", thread_id=thread_id or generate_thread_id())

    stock = Counter({k: int(v) for k, v in components.items() if int(v) > 0})
    crafted: list[CompletedItemName] = []
    crafted_map: dict[ChampionName, list[CompletedItemName]] = {}

    for carry, desired in bis_by_carry.items():
        crafted_map.setdefault(carry, [])
        for item in desired:
            recipe = recipes.get(item)
            if not recipe:
                continue  # Unknown recipe → skip silently to keep UX forgiving
            need = Counter(recipe)
            # Check feasibility
            feasible = all(stock.get(comp, 0) >= qty for comp, qty in need.items())
            if not feasible:
                continue
            # Consume components
            for comp, qty in need.items():
                stock[comp] -= qty
                if stock[comp] <= 0:
                    del stock[comp]
            crafted.append(item)
            crafted_map[carry].append(item)
            if per_carry_limit is not None and len(crafted_map[carry]) >= per_carry_limit:
                break

    result = CraftResult(
        crafted=crafted,
        crafted_per_carry=crafted_map,
        remaining_components=dict(stock),
    )

    log.info(
        "Greedy crafting result",
        total=len(crafted),
        carries=sum(1 for v in crafted_map.values() if v),
        unique_remaining=len(result.remaining_components),
    )
    return result
