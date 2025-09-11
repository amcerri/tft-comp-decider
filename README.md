# TFT Comp Decider

A stage‑aware **Teamfight Tactics** composition decider with a transparent scoring engine and a simple Streamlit UI.

---

- [TFT Comp Decider](#tft-comp-decider)
  - [Quickstart](#quickstart)
  - [Overview](#overview)
  - [Roadmap (Phases)](#roadmap-phases)
  - [Architecture](#architecture)
  - [Data \& Files](#data--files)
    - [Catalog (per patch)](#catalog-per-patch)
    - [Builds](#builds)
  - [Scoring (high level)](#scoring-high-level)
  - [UI (Streamlit)](#ui-streamlit)
  - [Troubleshooting](#troubleshooting)
  - [Development](#development)
  - [Logging](#logging)
  - [Contributing](#contributing)
  - [License](#license)

---

## Quickstart

**Requirements:** Python 3.11+

```bash
# 1) Create a virtualenv and install (with dev tools)
make install

# 2) Run the app
make run

# 3) (Optional) Lint, type‑check, and test
make check
```

If you prefer not to use `make`:
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
streamlit run src/tft_decider/ui/app.py
```

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

- [x] **Foundation**: licensing, toolchain, scaffold
- [x] **Infra**: package init + structured logging helpers
- [x] **Core contracts**: types & exceptions
- [x] **Domain models**: Pydantic models for builds & inventory
- [x] **Catalog**: YAML loader for champions and item components per patch
- [x] **Builds loader**: YAML loader + two example builds
- [x] **Engine (solver & scoring)**: item assignment + stage‑aware scoring (no augments in score)
- [x] **Notes engine**: banners with triggers (e.g., missing augment → pivot suggestion)
- [x] **UI**: Streamlit app (selection, stage, forced build, links, top‑N)
- [x] **Tests**: smoke tests for scoring and notes
- [x] **Dev UX (opt.)**: Makefile, README updates

> The roadmap will evolve. Contributions with additional builds/patches are welcome.

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
- **Tier prior**: S/A/B/C/X plus rank within tier.

> Augments do **not** influence the numeric score; they only trigger **notes/banners** (e.g., “missing Double Trouble → pivot to Sniper Squad”).

---

## UI (Streamlit)

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

## Troubleshooting

**Can't load catalog or builds (file not found)?**
- Paths are resolved relative to the code. By default the app expects:
  - Catalog: `data/catalog/15.4_en.yaml`
  - Builds dir: `data/builds/`
- If your data lives elsewhere, set an absolute path via the environment variable:
  ```bash
  TFT_DATA_DIR=/absolute/path/to/data streamlit run src/tft_decider/ui/app.py
  # or with make
  TFT_DATA_DIR=/absolute/path/to/data make run
  ```
  On PowerShell (Windows):
  ```powershell
  $env:TFT_DATA_DIR="C:\\path\\to\\data"; streamlit run src/tft_decider/ui/app.py
  ```

**Verify files exist**
```bash
ls -la data/catalog/15.4_en.yaml
ls -la data/builds/
```

**Port already in use?**
```bash
streamlit run src/tft_decider/ui/app.py --server.port 8502
```

**Telemetry prompt / watchdog note**
- The first run may show a telemetry prompt; it is safe to skip.
- For faster file watching, you can install watchdog: `pip install watchdog`.

## Development

Lint, type‑check, and tests:
```bash
ruff check .
black .
mypy src
pytest
```
Or simply:
```bash
make check
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

This repository is public but aimed at personal, non‑commercial use. Feel free to open issues and PRs. Please follow PEP 8/257, keep all strings in English, and adhere to the logging contract above.

---

## License

[MIT](LICENSE)