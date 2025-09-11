# TFT Comp Decider

A stage‑aware **Teamfight Tactics** composition decider with a transparent scoring engine and a simple Streamlit UI.

> Status: project scaffold and core plan in progress. The repository follows a phased roadmap (see below).

---

## Overview

**TFT Comp Decider** helps you choose the best composition for your current board by comparing your
owned **champions**, **item components**, and **augments** (for notes only) against a curated library of builds.

- **Stage‑aware** champion matching (early / mid / late compositions).
- **Item‑driven** matching using ordered component priority (+ optional BiS hints).
- **Tier‑aware** prior that incorporates S/A/B/C/X and rank within tier.
- **Notes/Banners** (info/warning/critical) for pivot guidance — augments influence notes only, not the score.
- **Force build**: manually pin a build to the top regardless of score.
- **Patch‑pinned catalog**: local YAML for champions/components (offline friendly).

The scoring is **explainable** and designed to be tuned. It does not require scraping — all data is either local YAML or maintained by you.

---

## Roadmap (Phases)

1. **Foundation**: licensing, toolchain, scaffold (done)
2. **Infra**: package init + structured logging helpers
3. **Core contracts**: types & exceptions
4. **Domain models**: Pydantic models for builds & inventory
5. **Catalog**: YAML loader for champions and item components per patch
6. **Builds loader**: YAML loader + two example builds
7. **Engine (solver & scoring)**: item assignment + stage‑aware scoring (no augments in score)
8. **Notes engine**: banners with triggers (e.g., missing augment → pivot suggestion)
9. **UI**: Streamlit app (selection, stage, forced build, links, top‑N)
10. **Tests**: smoke tests for scoring and notes
11. **Dev UX (opt.)**: pre‑commit, Makefile, README updates

> The README may reference components that land in later phases; commands below specify when something becomes available.

---

## Architecture

```
src/
  tft_decider/
    __init__.py
    infra/
      logging.py        # structlog configuration & helpers
    core/
      types.py          # enums & type aliases
      exceptions.py     # domain exceptions
      models.py         # Pydantic models (Build, Inventory, etc.)
      solver.py         # item matching heuristics
      scoring.py        # stage-aware scoring (champions+items+tier prior)
      notes.py          # banners evaluation (info/warning/critical)
    data/
      catalog.py        # YAML catalog loader (champions, components, etc.)
    ui/
      texts.py          # UI strings in English
      app.py            # Streamlit app

data/
  catalog/
    15.4_en.yaml       # example patch catalog (editable)
  builds/
    double_trouble_fan_service.yaml
    sniper_squad.yaml
```

---

## Data & Files

### Catalog (per patch)
A minimal, versioned YAML file containing **champions**, **item components**, and optional **completed items**, **augments**, **traits** for a specific patch.

- File: `data/catalog/<patch>_en.yaml` (e.g., `15.4_en.yaml`)
- Loader: `src/tft_decider/data/catalog.py`

Example (excerpt):
```yaml
patch: "15.4"
language: "en"
champions: ["Xayah", "Rakan", "Janna", "Neeko", "Yasuo", "K'Sante"]
items_components: [
  "B. F. Sword", "Recurve Bow", "Needlessly Large Rod", "Tear of the Goddess",
  "Chain Vest", "Negatron Cloak", "Giant's Belt", "Sparring Gloves"
]
```

### Builds
Each build is a YAML with **core units**, **early/mid/late comps**, **ordered item components**, optional **BiS per carry**, **links**, and **notes** with severities.

- Directory: `data/builds/*.yaml`
- Loader: `src/tft_decider/data/data_loader.py`

---

## Scoring (high level)

The total score combines stage‑aware **champion presence**, **item component alignment**, and a **tier prior**:

```
score = wC * ScoreChampions(stage) + wI * ScoreItems + wP * TierPrior
```

- **Champions**: presence across early/mid/late comps with weight by current stage and core unit emphasis.
- **Items**: ordered component priority matching + small bonus if BiS becomes feasible.
- **Tier prior**: S/S/A/B/C/X plus rank within tier.

> Augments do **not** influence the numeric score; they only trigger **notes/banners** (e.g., “missing Double Trouble → pivot to Sniper Squad”).

---

## UI (Streamlit)

**Available after Phase 9.**

Run the app:
```bash
streamlit run src/tft_decider/ui/app.py
```
Key actions in the UI:
- Select owned champions, item components, and augments (for notes only).
- Choose the **stage** (e.g., `2-1`, `3-2`, `4-1`).
- Toggle **Force build** to pin a build to the top.
- See **Top N** suggestions with scores, links to external guides, and **banners** with pivot suggestions.

---

## Requirements

- Python **3.11+**
- macOS/Linux/Windows supported (tested locally on macOS)

Install (development):
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e ".[dev]"
```

Install (runtime only):
```bash
pip install -e "."
```

Run tests (after Phase 10):
```bash
pytest
```

Lint & format:
```bash
ruff check .
black .
mypy src
```

---

## Logging

The project uses **structlog**. All logs include the structured fields `component`, `event`, and `thread_id`.

Example:
```python
logger.bind(component="ui.app", event="score", thread_id=thread_id).info(
    "Computed scores for top builds", top_n=len(rows)
)
```

---

## Contributing

This repository is public but aimed at personal, non-commercial use. Feel free to open issues and PRs. Please follow PEP 8/257, keep all strings in English, and adhere to the logging contract above.

---

## License

[MIT](LICENSE)