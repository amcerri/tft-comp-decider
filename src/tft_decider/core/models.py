"""
Domain data models (Pydantic) for builds, notes, and user inventory.

Overview
--------
Define strongly-typed, validated data structures for:
- Build definitions (core units, early/mid/late comps, item priorities, links, notes).
- Notes & triggers (info/warning/critical) used by the banners engine.
- User inventory (owned champions, item components, augments, current stage).

Design
------
- Use Pydantic v2 models for input validation and normalization.
- Keep this module self-contained; only import from ``tft_decider.core.types``.
- Avoid importing solver/scoring logic to prevent circular dependencies.
- Normalize names (champions/items) to consistent forms (trim, strip trailing "*").

Integration
-----------
Loaded by data providers (YAML loaders) and consumed by the scoring and notes
engines, as well as the UI. Safe to import early and from tests.

Usage
-----
>>> inv = Inventory(units={"Xayah": 2}, items_components={"Recurve Bow": 1}, stage="3-2")
>>> build = Build(id="sniper_squad", name="Sniper Squad", tier="A", tier_rank=1,
...               patch="15.4", early_comp=["Gnar", "Kennen"], mid_comp=["Sivir"],
...               late_comp=["Jhin", "Neeko"], item_priority_components=["Chain Vest"]) 
>>> build.core_unit_names()
['Gnar', 'Kennen', 'Sivir', 'Jhin', 'Neeko']
"""

from __future__ import annotations

from typing import Final, Optional

from pydantic import BaseModel, Field, field_validator

from tft_decider.core.types import (
    AugmentName,
    BuildId,
    ChampionName,
    ComponentName,
    CompletedItemName,
    JsonDict,
    StageString,
    UrlStr,
    Severity,
    StageBucket,
    parse_stage,
)

__all__: Final[list[str]] = [
    "CoreUnit",
    "Link",
    "NoteTriggers",
    "Note",
    "Build",
    "Inventory",
]

# ---------------------------------------------------------------------------
# Helpers & constants
# ---------------------------------------------------------------------------
TIER_ALLOWED: Final[set[str]] = {"S", "A", "B", "C", "X"}


def _normalize_name(value: str) -> str:
    """Normalize a domain name (champion/item/augment).

    Removes surrounding whitespace and a trailing '*' marker that some guides use
    to denote core units. The normalized value is returned.

    Args:
        value: The raw name.

    Returns:
        The normalized name.
    """

    value = (value or "").strip()
    if value.endswith("*"):
        value = value[:-1].rstrip()
    return value


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class CoreUnit(BaseModel):
    """Describe a core unit for a build.

    Attributes:
        name: Champion name.
        star_goal: Desired star level (1–3).
        required: Whether the unit is mandatory for the build to be considered.
    """

    name: ChampionName
    star_goal: int = Field(default=2, ge=1, le=3)
    required: bool = False

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        return _normalize_name(v)


class Link(BaseModel):
    """Represent an external link associated with a build (guides, videos)."""

    label: str
    url: UrlStr

    @field_validator("label")
    @classmethod
    def _v_label(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("label must be non-empty")
        return v

    @field_validator("url")
    @classmethod
    def _v_url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class NoteTriggers(BaseModel):
    """Define conditions that trigger a note/banner.

    Fields are optional; if multiple are set, all must evaluate truthy for the
    note to fire (logical AND of the active conditions).
    """

    missing_augments_any: list[AugmentName] = Field(default_factory=list)
    have_components_any: list[ComponentName] = Field(default_factory=list)
    stage_min: Optional[StageString] = None
    suggest_pivot_to: Optional[BuildId] = None

    @field_validator("missing_augments_any", "have_components_any")
    @classmethod
    def _v_lists(cls, values: list[str]) -> list[str]:
        return [_normalize_name(v) for v in values]

    @field_validator("stage_min")
    @classmethod
    def _v_stage(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        # Validate format via parse_stage; keep original string if valid.
        parse_stage(v)
        return v


class Note(BaseModel):
    """Represent a note/banner with severity and trigger conditions."""

    severity: Severity
    text: str
    triggers: NoteTriggers

    @field_validator("text")
    @classmethod
    def _v_text(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("text must be non-empty")
        return v


class Build(BaseModel):
    """Represent a TFT build definition.

    The model intentionally keeps item representation simple: ordered **item
    components** (by priority) and optional **completed items** per carry (BiS).
    """

    id: BuildId
    name: str
    tier: str = Field(description="One of S, A, B, C, X")
    tier_rank: int = Field(default=1, ge=1)
    patch: str

    core_units: list[CoreUnit] = Field(default_factory=list)
    early_comp: list[ChampionName] = Field(default_factory=list)
    mid_comp: list[ChampionName] = Field(default_factory=list)
    late_comp: list[ChampionName] = Field(default_factory=list)

    item_priority_components: list[ComponentName] = Field(default_factory=list)
    bis_items: dict[ChampionName, list[CompletedItemName]] = Field(default_factory=dict)

    links: list[Link] = Field(default_factory=list)
    notes: list[Note] = Field(default_factory=list)

    # -------------------------
    # Validators & normalizers
    # -------------------------
    @field_validator("id")
    @classmethod
    def _v_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("id must be non-empty")
        return v

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must be non-empty")
        return v

    @field_validator("tier")
    @classmethod
    def _v_tier(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in TIER_ALLOWED:
            raise ValueError(f"tier must be one of {sorted(TIER_ALLOWED)}")
        return v

    @field_validator("early_comp", "mid_comp", "late_comp", mode="before")
    @classmethod
    def _v_comp_lists(cls, values: list[str]) -> list[str]:
        # Normalize champion names and drop empties
        return [n for n in (_normalize_name(v) for v in (values or [])) if n]

    @field_validator("item_priority_components", mode="before")
    @classmethod
    def _v_item_components(cls, values: list[str]) -> list[str]:
        return [n for n in (_normalize_name(v) for v in (values or [])) if n]

    @field_validator("bis_items")
    @classmethod
    def _v_bis(cls, mapping: dict[str, list[str]]) -> dict[str, list[str]]:
        normalized: dict[str, list[str]] = {}
        for carry, items in (mapping or {}).items():
            key = _normalize_name(carry)
            normalized[key] = [i.strip() for i in items if i and i.strip()]
        return normalized

    # -------------------------
    # Convenience helpers
    # -------------------------
    def all_unit_names(self) -> list[ChampionName]:
        """Return the union of all champion names referenced by the build.

        Returns:
            A list of unique champion names across core/early/mid/late comps.
        """

        names: list[str] = [cu.name for cu in self.core_units]
        for group in (self.early_comp, self.mid_comp, self.late_comp):
            names.extend(group)
        # Deduplicate preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for n in names:
            if n not in seen:
                unique.append(n)
                seen.add(n)
        return unique


class Inventory(BaseModel):
    """Represent the user's current inventory and context.

    Attributes:
        units: Mapping from champion name to current star level (0–3).
        items_components: Mapping from component name to count owned.
        items_completed: Optional list of completed item names.
        augments: Owned augments (used for notes only; not for scoring).
        stage: Current stage string (e.g., ``"3-2"``).
    """

    units: dict[ChampionName, int] = Field(default_factory=dict)
    items_components: dict[ComponentName, int] = Field(default_factory=dict)
    items_completed: list[CompletedItemName] = Field(default_factory=list)
    augments: list[AugmentName] = Field(default_factory=list)
    stage: StageString = "3-2"

    @field_validator("units")
    @classmethod
    def _v_units(cls, mapping: dict[str, int]) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for raw_name, stars in (mapping or {}).items():
            name = _normalize_name(raw_name)
            if stars < 0 or stars > 3:
                raise ValueError(f"invalid star count for '{name}': {stars} (must be 0..3)")
            normalized[name] = int(stars)
        return normalized

    @field_validator("items_components")
    @classmethod
    def _v_components(cls, mapping: dict[str, int]) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for raw_name, count in (mapping or {}).items():
            name = _normalize_name(raw_name)
            if count < 0:
                raise ValueError(f"invalid component count for '{name}': {count} (must be >= 0)")
            normalized[name] = int(count)
        return normalized

    @field_validator("augments")
    @classmethod
    def _v_augments(cls, values: list[str]) -> list[str]:
        return [_normalize_name(v) for v in (values or [])]

    @field_validator("stage")
    @classmethod
    def _v_stage(cls, v: str) -> str:
        # Validate format via parse_stage; keep original string if valid.
        parse_stage(v)
        return v
