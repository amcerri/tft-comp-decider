#!/usr/bin/env python3
"""Generate build YAML files by scraping TFTAcademy tier list data.

Usage
-----
    python scripts/update_builds.py

The script fetches the public comps tier list, converts the embedded JSON-like
payload into Python objects, normalises champion/item names using the local
catalog, and finally writes a fresh set of build YAML files under
``data/builds``. By default any existing ``*.yaml`` in that directory are
removed before regeneration.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Iterable, Iterator, Mapping, Optional

import pyjson5
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tft_decider.data.catalog import Catalog, load_catalog_from_yaml
from tft_decider.infra.logging import generate_thread_id, logger_for, setup_logging


TFTACADEMY_URL = "https://tftacademy.com/tierlist/comps"
GUIDES_KEY = "guides"


@dataclass(slots=True)
class GuideEntry:
    """Minimal data extracted from TFTAcademy for a single composition."""

    raw: dict
    tier: str
    display_index: int
    slug: str
    title: str
    is_public: bool


@dataclass(slots=True)
class GeneratedBuild:
    """Representation of a build ready to be serialised into YAML."""

    id: str
    name: str
    tier: str
    tier_rank: int = 0
    patch: str = ""
    core_units: list[dict[str, object]] = field(default_factory=list)
    early_comp: list[str] = field(default_factory=list)
    mid_comp: list[str] = field(default_factory=list)
    late_comp: list[str] = field(default_factory=list)
    item_priority_components: list[str] = field(default_factory=list)
    bis_items: dict[str, list[str]] = field(default_factory=dict)
    links: list[dict[str, str]] = field(default_factory=list)
    notes: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """Return a serialisable dictionary preserving field order."""

        data: dict[str, object] = {
            "id": self.id,
            "name": self.name,
            "tier": self.tier,
            "tier_rank": self.tier_rank,
            "patch": self.patch,
            "core_units": self.core_units,
            "early_comp": self.early_comp,
            "mid_comp": self.mid_comp,
            "late_comp": self.late_comp,
            "item_priority_components": self.item_priority_components,
        }
        if self.bis_items:
            data["bis_items"] = self.bis_items
        if self.links:
            data["links"] = self.links
        if self.notes:
            data["notes"] = self.notes
        return data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update build YAML files from TFTAcademy")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/builds"),
        help="Directory where build YAMLs will be written (default: data/builds)",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("data/catalog/15.4_en.yaml"),
        help="Catalog YAML used for name normalisation (default: data/catalog/15.4_en.yaml)",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Do not delete pre-existing YAML files before writing new ones",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and log the number of builds without writing files",
    )
    return parser.parse_args()


def fetch_guides(log, session: Optional[requests.Session] = None) -> tuple[list[GuideEntry], str]:
    """Fetch the TFTAcademy page and extract the guides payload."""

    sess = session or requests.Session()
    resp = sess.get(TFTACADEMY_URL, timeout=30)
    resp.raise_for_status()
    html = resp.text

    marker = "node_ids: [0, 9, 10, 63]"
    pivot = html.find(marker)
    if pivot == -1:
        raise RuntimeError("Could not locate Svelte payload in response")

    data_start = html.find("data:", pivot)
    if data_start == -1:
        raise RuntimeError("Could not find data array after node_ids marker")

    array_str, _ = extract_js_array(html[data_start + len("data:") :])
    entries = pyjson5.loads(array_str)

    patch = ""
    guides_raw: list[dict] = []
    for entry in entries:
        data = entry.get("data")
        if not isinstance(data, dict):
            continue
        if "patch" in data and not patch:
            patch = str(data.get("patch", ""))
        if GUIDES_KEY in data:
            guides_raw = data[GUIDES_KEY]
            break

    if not guides_raw:
        raise RuntimeError("No guides payload found in TFTAcademy response")

    guides: list[GuideEntry] = []
    for raw in guides_raw:
        slug = str(raw.get("compSlug", "")).strip()
        tier = str(raw.get("tier", "")).strip().upper() or "B"
        display_idx = int(raw.get("displayIndex", 0))
        title = str(raw.get("title", slug)).strip() or slug
        is_public = bool(raw.get("isPublic", True))
        guides.append(GuideEntry(raw=raw, tier=tier, display_index=display_idx, slug=slug, title=title, is_public=is_public))

    log.info("Fetched guides", count=len(guides), patch=patch)
    return guides, patch


def extract_js_array(data: str) -> tuple[str, str]:
    """Extract the first array literal from the provided string."""

    idx = 0
    while idx < len(data) and data[idx].isspace():
        idx += 1
    if idx >= len(data) or data[idx] != "[":
        raise RuntimeError("Expected '[' at start of JS array")

    level = 0
    for end in range(idx, len(data)):
        ch = data[end]
        if ch == "[":
            level += 1
        elif ch == "]":
            level -= 1
            if level == 0:
                return data[idx : end + 1], data[end + 1 :]
    raise RuntimeError("Unbalanced brackets while extracting JS array")
def normalise_key(value: str) -> str:
    """Return a normalised key (alphanumeric, lower-case)."""

    return re.sub(r"[^A-Za-z0-9]", "", value).lower()


def api_name_to_key(api_name: str) -> str:
    """Normalise a TFT API name (champion/item) into our key format."""

    token = re.sub(r"^TFT\d*_", "", api_name)
    token = re.sub(r"^TFT_Item_", "", token)
    token = re.sub(r"^TFT\d*_Item_", "", token)
    token = re.sub(r"^Item_", "", token)
    token = re.sub(r"^Item_Artifact_", "", token)
    token = token.replace("_", "")
    return normalise_key(token)


class CatalogIndex:
    """Helper that exposes fast lookup tables for catalog entities."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self._champion_map = self._build_champion_map()
        self._cost_map = self._build_cost_map()
        self._component_map = self._build_component_map()
        self._completed_map = self._build_completed_items_map()
        self._aliases = {
            "galio": "Galio",
            "zyragraspingplant": "Zyra",
        }

    def _build_champion_map(self) -> Mapping[str, str]:
        mapping: dict[str, str] = {}
        for entry in self.catalog.champions_index:
            mapping.setdefault(normalise_key(entry.name), entry.name)
        for name in self.catalog.champions:
            mapping.setdefault(normalise_key(name), name)
        return mapping

    def _build_cost_map(self) -> Mapping[str, int]:
        mapping: dict[str, int] = {}
        for entry in self.catalog.champions_index:
            mapping[normalise_key(entry.name)] = entry.cost
        return mapping

    def _build_component_map(self) -> Mapping[str, str]:
        mapping: dict[str, str] = {}
        for name in self.catalog.items_components:
            mapping[normalise_key(name)] = name
        return mapping

    def _build_completed_items_map(self) -> Mapping[str, tuple[str, list[str]]]:
        mapping: dict[str, tuple[str, list[str]]] = {}
        for item in self.catalog.items_completed:
            mapping[normalise_key(item.name)] = (item.name, list(item.components))
        return mapping

    def resolve_champion(self, api_name: str) -> Optional[str]:
        key = api_name_to_key(api_name)
        resolved = self._champion_map.get(key)
        if resolved:
            return resolved
        alias = self._aliases.get(key)
        if alias:
            return alias
        return None

    def cost_of(self, name: str) -> Optional[int]:
        return self._cost_map.get(normalise_key(name))

    def resolve_item(self, api_name: str) -> Optional[str]:
        key = api_name_to_key(api_name)
        if key in self._completed_map:
            return self._completed_map[key][0]
        if key in self._component_map:
            return self._component_map[key]
        return None

    def components_for(self, item_name: str) -> list[str]:
        key = normalise_key(item_name)
        if key in self._completed_map:
            _, components = self._completed_map[key]
            return list(components)
        if key in self._component_map:
            return [self._component_map[key]]
        return []


def generate_builds(log, guides: Iterable[GuideEntry], catalog_index: CatalogIndex, patch: str) -> list[GeneratedBuild]:
    builds: list[GeneratedBuild] = []
    selected: list[tuple[GuideEntry, GeneratedBuild]] = []
    for guide in guides:
        if not guide.is_public or not guide.slug:
            continue
        build = build_from_guide(log, guide, catalog_index)
        if build is None:
            log.warning("Skipping guide due to unresolved entities", slug=guide.slug)
            continue
        build.patch = patch
        builds.append(build)

        selected.append((guide, build))

    # Assign tier ranks by tier bucket using display index ordering.
    tiers: dict[str, list[tuple[int, GeneratedBuild]]] = defaultdict(list)
    for guide, build in selected:
        tiers[build.tier].append((guide.display_index, build))

    for tier, entries in tiers.items():
        for rank, (_, build) in enumerate(sorted(entries, key=lambda item: item[0]), start=1):
            build.tier_rank = rank

    builds.sort(key=lambda b: ("SABCDX".find(b.tier) if b.tier in "SABCDX" else 99, b.tier_rank, b.name.lower()))
    log.info("Generated builds", count=len(builds))
    return builds


def build_from_guide(log, guide: GuideEntry, catalog_index: CatalogIndex) -> Optional[GeneratedBuild]:
    slug = guide.slug.replace("/", "_")
    build = GeneratedBuild(id=slug, name=guide.title, tier=guide.tier)

    # Early / late comp
    early_comp_raw = guide.raw.get("earlyComp", [])
    late_comp_raw = guide.raw.get("finalComp", [])

    early_comp: list[str] = []
    missing_early: list[str] = []
    for entry in early_comp_raw:
        resolved = catalog_index.resolve_champion(entry.get("apiName", ""))
        if resolved:
            early_comp.append(resolved)
        else:
            missing_early.append(entry.get("apiName", ""))

    late_comp: list[str] = []
    missing_late: list[str] = []
    for entry in late_comp_raw:
        resolved = catalog_index.resolve_champion(entry.get("apiName", ""))
        if resolved:
            late_comp.append(resolved)
        else:
            missing_late.append(entry.get("apiName", ""))

    if not late_comp:
        log.warning("No resolvable late comp champions", slug=guide.slug)
        return None

    if missing_late:
        log.warning(
            "Dropping unresolved champions from late comp",
            slug=guide.slug,
            missing=missing_late,
        )

    if missing_early:
        log.warning(
            "Dropping unresolved champions from early comp",
            slug=guide.slug,
            missing=missing_early,
        )

    build.early_comp = early_comp
    build.late_comp = late_comp

    # Mid comp: take unique champions present in late_comp that have cost <=3 or appear in early comp.
    early_set = {normalise_key(name) for name in build.early_comp}
    mid_names: list[str] = []
    seen_mid: set[str] = set()
    for api_entry in late_comp_raw:
        resolved = catalog_index.resolve_champion(api_entry.get("apiName", ""))
        if not resolved:
            continue
        key = normalise_key(resolved)
        if key in seen_mid:
            continue
        cost = catalog_index.cost_of(resolved) or 0
        stars = int(api_entry.get("stars", 1))
        if key in early_set or cost <= 3 or stars >= 3:
            mid_names.append(resolved)
            seen_mid.add(key)
    build.mid_comp = mid_names

    # Core units: main champion + any final comp with stars >=3
    core_units: list[dict[str, object]] = []
    main = guide.raw.get("mainChampion") or {}
    main_name = catalog_index.resolve_champion(main.get("apiName", ""))
    if main_name:
        cost = catalog_index.cost_of(main_name) or 1
        star_goal = 3 if cost <= 3 else 2
        core_units.append({"name": main_name, "star_goal": star_goal, "required": True})

    for entry in late_comp_raw:
        resolved = catalog_index.resolve_champion(entry.get("apiName", ""))
        if not resolved:
            continue
        stars = int(entry.get("stars", 1))
        if stars >= 3 and (not main_name or resolved != main_name):
            core_units.append({"name": resolved, "star_goal": stars, "required": False})
    build.core_units = core_units

    # BiS items per carry
    bis: dict[str, list[str]] = {}
    for entry in late_comp_raw:
        resolved = catalog_index.resolve_champion(entry.get("apiName", ""))
        if not resolved:
            continue
        items = [catalog_index.resolve_item(api) for api in entry.get("items", [])]
        filtered = [item for item in items if item]
        if filtered:
            bis[resolved] = filtered
    build.bis_items = bis

    # Item priority components: derive from carousel and BiS items.
    priority: list[str] = []
    seen_components: set[str] = set()

    def add_components_from_item(item_name: str) -> None:
        for component in catalog_index.components_for(item_name):
            key = normalise_key(component)
            if key not in seen_components:
                priority.append(component)
                seen_components.add(key)

    for item_api in guide.raw.get("carousel", []):
        resolved_item = catalog_index.resolve_item(item_api.get("apiName", ""))
        if not resolved_item:
            continue
        add_components_from_item(resolved_item)

    for items in bis.values():
        for item_name in items:
            add_components_from_item(item_name)

    build.item_priority_components = priority

    # Notes based on tips / augments tip
    notes: list[dict[str, object]] = []
    for tip in guide.raw.get("tips", []):
        stage_label = str(tip.get("stage", "")).strip().upper()
        text = str(tip.get("tip", "")).strip()
        if not text:
            continue
        triggers: dict[str, object] = {}
        if stage_label:
            match = re.search(r"STAGE\s*(\d)", stage_label)
            if match:
                triggers["stage_min"] = f"{match.group(1)}-1"
        note = {"severity": "info", "text": text, "triggers": triggers}
        notes.append(note)

    aug_tip = str(guide.raw.get("augmentsTip", "")).strip()
    if aug_tip:
        notes.append({"severity": "info", "text": aug_tip, "triggers": {}})

    build.notes = notes

    # Link to TFTAcademy article
    build.links = [
        {
            "label": "TFT Academy Guide",
            "url": f"https://tftacademy.com/tierlist/comps/{guide.slug}",
        }
    ]

    return build


def write_builds(log, builds: Iterable[GeneratedBuild], output_dir: Path, keep_existing: bool) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not keep_existing:
        for path in output_dir.glob("*.yaml"):
            path.unlink()

    for build in builds:
        path = output_dir / f"{build.id}.yaml"
        header = "# Auto-generated by scripts/update_builds.py\n# Source: https://tftacademy.com/tierlist/comps\n"
        yaml_payload = yaml.safe_dump(
            build.to_dict(),
            sort_keys=False,
            allow_unicode=True,
        )
        path.write_text(header + "\n" + yaml_payload, encoding="utf-8")
        log.info("Wrote build", path=str(path))


def main() -> None:
    args = parse_args()
    setup_logging()
    thread_id = generate_thread_id()
    log = logger_for(component="scripts.update_builds", event="run", thread_id=thread_id)

    catalog_path = args.catalog
    catalog = load_catalog_from_yaml(str(catalog_path), thread_id=thread_id)
    catalog_index = CatalogIndex(catalog)

    guides, patch = fetch_guides(log, session=requests.Session())
    builds = generate_builds(log, guides, catalog_index, patch or catalog.patch)

    if args.dry_run:
        log.info("Dry run complete", builds=len(builds))
        return

    write_builds(log, builds, args.output, keep_existing=args.keep_existing)


if __name__ == "__main__":
    main()
