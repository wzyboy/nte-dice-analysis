# Changelog

All notable changes to this project will be documented in this file.

This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.7.0 - 2026-08-19

### Added

- Track arc-research pity and history against limited S-Class arcs, while reporting averages for both limited and all S-Class arcs.

## 0.6.3 - 2026-08-11

### Changed

- Update known item corrections for the latest banners.

## 0.6.2 - 2026-07-30

### Added

- Add a repository skill for updating known items from official banner announcements.

### Changed

- Refresh and reorganize known item corrections.

## 0.6.1 - 2026-07-29

### Changed

- Update known item corrections for the latest banners.

## 0.6.0 - 2026-07-08

### Added

- Add a guarded 2x-upscaled OCR retry for item names that need correction.

### Fixed

- Fix matching for item names with a single incorrect character.

## 0.5.2 - 2026-07-07

### Changed

- Update known item corrections for the latest banners.

## 0.5.1 - 2026-06-27

### Added

- Add a dedicated upscaled OCR fallback for missing or malformed date-column text.

### Changed

- Change captured screenshot filenames to use the capture timestamp and sequence number.
- Refresh the GUI screenshot in the documentation.

### Fixed

- Recover timestamps when OCR drops Chinese date markers or joins date and time digits.
- Preserve canonical timestamps already stored in JSON files.

## 0.5.0 - 2026-06-25

### Added

- Add Windows game screenshot capture from the GUI, using F9 to capture pages and F10 to finish.
- Add an elevated capture helper so screenshots can be captured when the game is running as administrator.

### Changed

- Document the new game screenshot capture workflow in the README and Windows package notes.

## 0.4.3 - 2026-06-25

### Fixed

- Fix deduplication when the same screenshot page is captured more than once.
- Reject duplicate Sleeping Land bonus rows within the same pull group.

## 0.4.2 - 2026-06-06

### Fixed

- Fix deduplication when identical or adjacent screenshot rows represent distinct records.

## 0.4.1 - 2026-06-02

### Added

- Add support for the Sleeping Land bonus pull.
- Add known item corrections for game version 1.1.

### Changed

- Split the GUI package into smaller modules.
- Add Ruff and pytest coverage tooling for development.

### Fixed

- Fix a typo in the XLSX header.

## 0.4.0 - 2026-06-01

### Added

- Add support for the Arc Research gacha pool type.
- Add `known_items.toml` for correcting item names that OCR may misread.
- Refresh displayed results when analysis runs without newly selected files.
- Add a three-column responsive grid for analysis output.

### Changed

- Enforce a stable gacha pool display order.
- Expand CI coverage with Ubuntu and Windows test jobs.

### Fixed

- Fix pie chart label overlap in generated visual output.
- Fix short-name OCR matching and refresh known item corrections.
- Fix minor text typos.

## 0.3.2 - 2026-05-31

### Fixed

- Fix test issues before release.

## 0.3.1 - 2026-05-31

### Added

- Add GUI actions for exporting PNG images and XLSX spreadsheets.
- Add graceful `KeyboardInterrupt` handling for the development app.

### Changed

- Reorganize summary generation into its own module.
- Refresh README screenshots and usage notes for the updated design.

## 0.3.0 - 2026-05-31

### Added

- Add copying analysis output as an image.
- Add simplified file and folder selection.
- Add automatic output handoff between advanced pipeline steps.
- Add loading of existing analysis data into the advanced window.
- Add display of the last analysis on app launch.
- Add the integrated dashboard with responsive pie charts and selectable statistics.
- Add supersampling and anti-aliasing for PNG export.

### Changed

- Restore the advanced-window layout.
- Update generated PNG examples in the documentation.
- Adjust the main window height and title.

### Fixed

- Fix stylesheet leakage between UI areas.
- Fix IO edge cases.
- Rename confusing buttons.

## 0.2.2 - 2026-05-30

### Added

- Add the GUI application icon.

### Changed

- Add the app icon to the README.

## 0.2.1 - 2026-05-30

### Fixed

- Fix row-boundary detection.
- Crop the title bar when screenshots come from windowed game mode.

## 0.2.0 - 2026-05-30

### Added

- Translate the GUI to Chinese.
- Use Microsoft YaHei for the GUI on Windows.

### Changed

- Simplify the README and update GUI screenshots.

## 0.1.2 - 2026-05-30

### Added

- Add a release helper script.

### Fixed

- Fix CI build issues.

## 0.1.0 - 2026-05-30

### Added

- Initial OCR pipeline for NTE gacha record screenshots.
- Add gacha pool, rarity, item type, pity count, and total pull count analysis.
- Add incremental importing, timestamp-based deduplication, and known item checks.
- Add XLSX and PNG export workflows.
- Add the GUI, default output folder, and Windows portable ZIP packaging.
- Add tests, linting, and build configuration.
