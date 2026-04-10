# Progress Log

## v0.1.0 — Backend Refactor (2026-04-08 → 2026-04-09)

### Completed

**Repo hygiene**
- Added `.gitignore`, removed committed `__pycache__/` and `egg-info/`
- Deleted orphan `VALID` file
- Pinned `requires-python >= 3.11`
- Added `pytest>=8` dev dependency

**Correctness fixes**
- Replaced all `datetime.utcnow()` with `datetime.now(timezone.utc)` (3.12+ deprecation)
- Fixed temperature decoding: packed `raw.value` now decoded via low-byte with sanity check; top-level `temperature.current` preferred
- Fixed wear-indicator conflation: `Wear_Leveling_Count` raw counter no longer misread as health percent; uses normalized column
- Fixed NVMe drives scoring false HEALTHY through the ATA path

**Architecture**
- Introduced `SmartSnapshot`, `Verdict`, `Finding`, `Confidence`, `VerdictResult` types (`models/smart_types.py`)
- Extracted `checks/smart/collector.py` with typed exceptions, 30s timeout, cross-platform `-d sat` retry
- Extracted `checks/smart/normalize.py` with `parse_ata()` and `parse_nvme()`
- Created `checks/smart/ata.py` (ATA evaluation rules) and `checks/smart/nvme.py` (NVMe evaluation rules)
- Verdict determined by worst finding, not score. Confidence gate prevents false PASS on insufficient data.

**CLI improvements**
- Extracted `_resolve_device()` — removed 3x copy-pasted device selection blocks
- `--json` without `--device` now fails cleanly instead of deadlocking on `input()`
- Added `--version` flag
- Added `__main__.py` for `python -m disk_health_checker`

**Output**
- New banner-first verdict format: verdict + confidence on one line, findings with `!!`/`!` markers, explicit "signals missing" section, actionable next steps
- Enriched JSON output with `findings[].evidence`, `device_kind`, NVMe fields, `confidence`

**Doctor command**
- Rewired to read findings from evaluation pipeline (supports ATA + NVMe) instead of re-checking raw detail keys

**macOS full workflow**
- Final recommendation now derives from `Verdict` (single source of truth) instead of parallel logic

**Tests**
- 130 tests across 9 test files
- Coverage: types, collector (monkeypatched), ATA normalize, NVMe normalize, ATA evaluate, NVMe evaluate, CLI, output formatting
- 3 synthetic NVMe fixtures (labeled)

**Docs & CI**
- README rewritten with examples, verdict/confidence guide, platform matrix, exit codes, finding codes
- GitHub Actions CI: Python 3.11, pytest on push/PR

### Known limitations
- Linux disk enumeration (`list_disks()`) returns empty — requires `--device` flag
- Legacy checks (filesystem, surface, stress, integrity) not upgraded to findings model
- NVMe fixtures are synthetic; field names should be verified against a real capture
- No `diskutil` timeout on macOS (can hang on stalled USB)
- `full` command does not run self-tests (recommend-only by design)

### Next steps
- GUI layer (PySide6 or Electron)
- Linux `lsblk` disk enumeration
- Real NVMe fixture capture and validation
- PyPI packaging
