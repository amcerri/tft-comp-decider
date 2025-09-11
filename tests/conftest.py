"""
Pytest configuration and shared fixtures.

Overview
--------
Provide test-wide fixtures for logging, catalog/build loading, recipes mapping,
and handy inventory builders. These fixtures keep tests concise and consistent.

Design
------
- Keep imports limited to already implemented modules.
- Load local YAML data (catalog/builds) from the repository paths.
- Expose small, typed factories for inventories used in scoring tests.

Integration
-----------
Imported implicitly by pytest. No side effects beyond optional logging setup.

Usage
-----
>>> # Example (inside a test module)
>>> def test_catalog_has_components(catalog):
...     assert len(catalog.items_components) >= 8
"""

from __future__ import annotations

from typing import Callable, Final, Optional

import pytest

from tft_decider.infra.logging import setup_logging, generate_thread_id
from tft_decider.data.catalog import Catalog, load_catalog_from_yaml
from tft_decider.data.data_loader import load_builds_from_dir
from tft_decider.core.models import Inventory

# ---------------------------------------------------------------------------
# Repository paths for data files used in tests
# ---------------------------------------------------------------------------
CATALOG_PATH: Final[str] = "data/catalog/15.4_en.yaml"
BUILDS_DIR: Final[str] = "data/builds"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _recipes_from_catalog(catalog: Catalog) -> dict[str, list[str]]:
    """Build a mapping of completed item → component recipe for tests.

    Args:
        catalog: Loaded catalog model.

    Returns:
        Mapping of completed item name to its component list.
    """

    recipes: dict[str, list[str]] = {}
    for item in catalog.items_completed:
        recipes[item.name] = list(item.components)
    return recipes


# ---------------------------------------------------------------------------
# Session-scoped fixtures (logging and data)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def thread_id() -> str:
    """Provide a session-wide correlation ID for structured logs."""

    return generate_thread_id()


@pytest.fixture(scope="session")
def logging_setup() -> None:
    """Initialize structlog so tests can emit structured logs if needed."""

    setup_logging()


@pytest.fixture(scope="session")
def catalog(logging_setup: None, thread_id: str) -> Catalog:  # noqa: PT004 - session fixture
    """Load the patch-pinned catalog used by UI selectors and recipes."""

    return load_catalog_from_yaml(CATALOG_PATH, thread_id=thread_id)


@pytest.fixture(scope="session")
def recipes(catalog: Catalog) -> dict[str, list[str]]:
    """Return completed item recipes derived from the catalog."""

    return _recipes_from_catalog(catalog)


@pytest.fixture(scope="session")
def builds(logging_setup: None, thread_id: str) -> list:
    """Load all example builds from the repository data directory."""

    return load_builds_from_dir(BUILDS_DIR, thread_id=thread_id)


# ---------------------------------------------------------------------------
# Function-scoped fixtures (inventory)
# ---------------------------------------------------------------------------

@pytest.fixture()
def inventory_factory() -> Callable[[Optional[dict[str, int]], Optional[dict[str, int]], Optional[list[str]], str], Inventory]:
    """Return a small factory to construct inventories for tests.

    The factory accepts optional dictionaries for units and components, plus
    augments and the stage string. Missing inputs default to empty values and
    ``stage='3-2'``.
    """

    def _make(
        units: Optional[dict[str, int]] = None,
        components: Optional[dict[str, int]] = None,
        augments: Optional[list[str]] = None,
        stage: str = "3-2",
    ) -> Inventory:
        return Inventory(
            units=units or {},
            items_components=components or {},
            augments=augments or [],
            stage=stage,
        )

    return _make


@pytest.fixture()
def sample_inventory(inventory_factory: Callable[..., Inventory]) -> Inventory:
    """Provide a small, realistic inventory useful across multiple tests.

    - Champions: Gnar, Kennen, Sivir, Jhin (1★ assumed).
    - Components: Chain Vest ×1, Negatron Cloak ×1, Recurve Bow ×1.
    - No augments; stage 3-2 (mid bucket).
    """

    return inventory_factory(
        units={"Gnar": 1, "Kennen": 1, "Sivir": 1, "Jhin": 1},
        components={"Chain Vest": 1, "Negatron Cloak": 1, "Recurve Bow": 1},
        augments=[],
        stage="3-2",
    )