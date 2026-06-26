# AGENTS.md

## Repo Conclusion

This is a Python 3.13 `uv` package for local OCR and analysis of NTE gacha record screenshots. It currently targets Simplified Chinese game screenshots and produces JSON intermediates plus PNG/XLSX summaries. Most behavior lives under `src/nte_dice_analysis`; tests under `tests` are the main specification.

## Commands

- Run the full test suite with `uv run pytest`.
- Run focused tests as `uv run pytest tests/test_dedup.py` or another specific file when iterating.
- Format/import-sort Python with `uv run ruff check --select I --fix src tests scripts packaging` and `uv run ruff format src tests scripts packaging`.
- Launch the GUI with `uv run nte-gui`.
- CLI entry points are `uv run nte-crop`, `uv run nte-recognize`, `uv run nte-export-xlsx`, `uv run nte-export-png`, and `uv run nte-check-known-items`.

## Windows Shell Encoding

PowerShell on Windows can default to a non-UTF-8 console encoding, which causes mojibake when commands print Chinese text. Before running project commands in PowerShell, set UTF-8 explicitly:

```powershell
chcp 65001 > $null
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = '1'
```

Keep this setup in the same PowerShell session before retrying `uv run ...`, `pytest`, or packaging commands. When reading or writing text files with PowerShell cmdlets, pass `-Encoding utf8` explicitly.

## Python Conventions

- Use Python 3.13 syntax and type hints.
- Prefer PEP 585 built-in generics such as `list[str]`.
- Use `str | None` and `A | B`; do not use `typing.Optional` or `typing.Union`.
- Do not add `from __future__ import annotations` unless a Python version constraint requires it.
- Prefer single quotes, small functions, and frozen dataclasses for data containers.
- Do not create classes for simple procedural features.
- The codebase uses PEP 695 `type` aliases in several modules; keep that style when adding aliases.

## Architecture Notes

- `models.py` defines canonical dataclasses and JSON row conversion. Treat `Record` fields and `OUTPUT_FIELDS` ordering as a cross-module contract.
- `constants.py` and `layouts.py` define crop boxes, row boundaries, column bounds, pool types, and dice-board vs arc-research layout differences.
- `pipeline.py` should stay thin: image normalization/cropping, pool detection, OCR table recognition, and optional debug-image writing.
- `ocr.py` owns PaddleOCR setup. OCR is CPU-only, expensive to initialize, and may download models unless bundled model dirs or `NTE_DICE_ANALYSIS_MODELS_DIR` are available. Avoid importing or initializing PaddleOCR at module import time.
- `records.py` converts OCR tokens into `Record` objects. It combines OCR text, known-item normalization, visual rarity detection, pip-count detection, and layout-specific row parsing.
- `dedup.py` is high-risk domain logic. It merges overlapping pages and validates pull groups, with different rules for dice-board and arc-research records. Add or update targeted tests for any change here.
- `export_records.prepare_export_records` is the export gate: load JSON, require timestamps, deduplicate, then require valid pull groups. Use it for new export paths.
- `summary.py`, `png.py`, and `xlsx.py` consume already prepared records. `xlsx.py` normalizes workbook archive details for deterministic output.
- `gui_workflow.py` is the testable orchestration layer shared by the GUI. Prefer putting workflow behavior there instead of inside Qt widgets.
- `src/nte_dice_analysis/gui/*` contains PySide6 UI code. User-facing Chinese strings belong in `gui_strings.py`; tests reject Han string literals directly inside the `gui` package.
- `capture.py`, `capture_helper.py`, and `gui/capture_hotkeys.py` contain Windows-specific capture and hotkey behavior. Keep tests fake-driven rather than requiring real Windows APIs.

## Data Flow

1. Full screenshots are normalized to the bottom 16:9 region when ratio-based crops are used.
2. Pool detection and table cropping produce `*.table.<pool_type>.png` files.
3. Cropped table images are recognized into OCR tokens, converted to `Record` objects, timestamp-validated, and written as JSON.
4. JSON files are loaded, deduplicated, pull-group validated, and exported to `records.xlsx`, `records.png`, and text summaries.

## Maintenance Guidance

- Add focused tests near changed behavior. The existing tests use fake OCR engines and fake platform APIs; follow that pattern instead of invoking real PaddleOCR or OS hotkeys in unit tests.
- Be careful changing crop defaults, row boundaries, column bounds, pool constants, or rarity labels. These affect OCR parsing, deduplication, summaries, PNG output, XLSX output, and GUI displays.
- Keep directory and file resolution deterministic by sorting paths case-insensitively, as existing IO helpers do.
- Preserve UTF-8 JSON behavior with `ensure_ascii=False`; screenshots and known-item data are Chinese-language user data.
- If dependencies appear missing, check the project environment first (`.venv`, `uv sync`, or `uv run ...`) before assuming a global install is needed.
