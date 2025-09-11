"""
Patch-pinned catalog loader for champions, item components, and more.

Overview
--------
Provide a small, validated data model and loader for a local YAML catalog that
lists champions, item components, optional completed items, augments, and traits
for a specific TFT patch. The catalog enables the UI to present full selectable
lists, independent of which builds are present.

Design
------
- Use Pydantic models for validation and normalization (names are trimmed and
  trailing core markers like '*' are removed).
- Keep this module self-contained; depend only on stdlib + pydantic + yaml and
  the previously created internal modules (types, exceptions, logging).
- Expose tiny helper functions to retrieve available champions and components.

Integration
-----------
The Streamlit UI and data loaders import this module to obtain full lists of
selectable domain entities. The catalog is versioned per patch under
``data/catalog/<patch>_en.yaml``.

Usage
-----
>>> from tft_decider.data.catalog import load_catalog_from_yaml, available_champions
>>> catalog = load_catalog_from_yaml("data/catalog/15.4_en.yaml")
>>> available_champions(catalog)[:3]
['Xayah', 'Rakan', 'Janna']
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from tft_decider.core.types import (
    AugmentName,
    ChampionName,
    ComponentName,
    CompletedItemName,
    StageString,
    TraitName,
)
from tft_decider.core.exceptions import CatalogLoadError, CatalogValidationError
from tft_decider.infra.logging import logger_for, generate_thread_id

__all__: Final[list[str]] = [
    "CompletedItem",
    "Trait",
    "Catalog",
    "load_catalog_from_yaml",
    "available_champions",
    "available_components",
    "available_augments",
    "available_traits",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_name(value: str) -> str:
    """Normalize a domain name by trimming and removing a trailing '*'.

    Args:
        value: The raw name.

    Returns:
        A clean, canonical string.
    """

    value = (value or "").strip()
    if value.endswith("*"):
        value = value[:-1].rstrip()
    return value


def _unique_preserve_order(values: list[str]) -> list[str]:
    """Return values deduplicated while preserving the original order."""

    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class CompletedItem(BaseModel):
    """Describe a completed item and the components that craft it."""

    name: CompletedItemName
    components: list[ComponentName] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:  # noqa: D401 - simple normalization
        return _normalize_name(v)

    @field_validator("components")
    @classmethod
    def _v_components(cls, values: list[str]) -> list[str]:
        cleaned = [_normalize_name(x) for x in (values or [])]
        # In TFT, completed items are crafted from 2 components, but we keep this
        # flexible to accommodate set-specific variations or special items.
        if len(cleaned) < 2:
            # Not an error — allow 1 or more to keep the schema flexible.
            pass
        return cleaned


class Trait(BaseModel):
    """Represent a trait and its activation breakpoints."""

    name: TraitName
    breakpoints: list[int] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        return _normalize_name(v)

    @field_validator("breakpoints")
    @classmethod
    def _v_breakpoints(cls, values: list[int]) -> list[int]:
        out: list[int] = [int(x) for x in (values or []) if int(x) > 0]
        return sorted(set(out))


class Catalog(BaseModel):
    """Represent a patch-pinned catalog of domain entities.

    Attributes:
        patch: Patch string (e.g., ``"15.4"``).
        language: Language code (e.g., ``"en"``).
        champions: All champions available in the patch.
        items_components: All base components (e.g., "Recurve Bow").
        items_completed: Optional completed items with component composition.
        augments: Optional list of augment names.
        traits: Optional list of traits and breakpoints.
    """

    patch: str
    language: str
    champions: list[ChampionName] = Field(default_factory=list)
    items_components: list[ComponentName] = Field(default_factory=list)
    items_completed: list[CompletedItem] = Field(default_factory=list)
    augments: list[AugmentName] = Field(default_factory=list)
    traits: list[Trait] = Field(default_factory=list)

    # -------------------------
    # Validators & normalizers
    # -------------------------
    @field_validator("patch")
    @classmethod
    def _v_patch(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("patch must be non-empty")
        return v

    @field_validator("language")
    @classmethod
    def _v_lang(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("language must be non-empty")
        return v

    @field_validator("champions", "items_components", "augments", mode="before")
    @classmethod
    def _v_lists(cls, values: list[str]) -> list[str]:
        cleaned = [x for x in (_normalize_name(v) for v in (values or [])) if x]
        return _unique_preserve_order(cleaned)


# ---------------------------------------------------------------------------
# Loader & accessors
# ---------------------------------------------------------------------------

def load_catalog_from_yaml(path: str, *, thread_id: Optional[str] = None) -> Catalog:
    """Load and validate a catalog YAML file.

    Args:
        path: The filesystem path to the YAML catalog.
        thread_id: Optional correlation ID for structured logging.

    Returns:
        A validated :class:`Catalog` instance.

    Raises:
        CatalogLoadError: When the file cannot be read or parsed.
        CatalogValidationError: When the YAML structure fails validation.
    """

    log = logger_for(component="data.catalog", event="load", thread_id=thread_id or generate_thread_id())
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError as exc:
        log.error("Catalog file not found", path=path)
        raise CatalogLoadError(path=path, reason="file not found") from exc
    except OSError as exc:
        log.error("Failed to open catalog file", path=path, error=str(exc))
        raise CatalogLoadError(path=path, reason=str(exc)) from exc
    except yaml.YAMLError as exc:  # pragma: no cover - parser variations
        log.error("Invalid YAML syntax", path=path, error=str(exc))
        raise CatalogLoadError(path=path, reason="invalid YAML") from exc

    try:
        catalog = Catalog(**(data or {}))
    except Exception as exc:
        # Pydantic error message is informative; wrap it for domain semantics.
        log.error("Catalog validation error", path=path, error=str(exc))
        raise CatalogValidationError(errors=[str(exc)]) from exc

    log.info("Catalog loaded", path=path, patch=catalog.patch, language=catalog.language,
             champions=len(catalog.champions), components=len(catalog.items_components))
    return catalog


def available_champions(catalog: Catalog) -> list[ChampionName]:
    """Return the list of champions from the catalog (deduplicated)."""

    return list(catalog.champions)


def available_components(catalog: Catalog) -> list[ComponentName]:
    """Return the list of item components from the catalog (deduplicated)."""

    return list(catalog.items_components)


def available_augments(catalog: Catalog) -> list[AugmentName]:
    """Return the list of augments from the catalog (may be empty)."""

    return list(catalog.augments)


def available_traits(catalog: Catalog) -> list[TraitName]:
    """Return the list of trait names from the catalog (may be empty)."""

    return [t.name for t in catalog.traits]