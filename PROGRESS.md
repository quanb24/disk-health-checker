# Progress Log

## v0.2.0 — Release (2026-04-12)

**Shipped.** All v0.2.0-dev features finalized plus:

- Safety fix: `run_full_suite()` now enforces `non_destructive` mode (skips stress/integrity with explicit UNKNOWN results)
- Schema fix: all error-state CheckResults include `health_score` for consistent schema
- 5 new ATA/USB test fixtures (healthy, failing, warning, UDMA CRC, USB half-blind)
- Expanded test_smart_scoring.py from 3 to 25 tests (full verdict/score/code coverage)
- Schema consistency tests for all 5 check types
- Full suite runner tests (9 tests covering safety guard, aggregate_status, global verdict)
- Version bumped to 0.2.0 across pyproject.toml and __init__.py
- 200+ total tests

---

## v0.2.0-dev — Linux Support, Unified Pipeline, Global Verdict, & Robustness (2026-04-10)

### Completed

**Global verdict engine**
- Created `verdict/` package with types, engine, and public API
- New types: `OverallHealth` (Healthy/Watch/Degrading/At Risk/Failing/Unknown), `Urgency` (No action → Replace now), `RecommendedUsage` (Primary → Retire), `GlobalConfidence`, `ConflictNote`, `GlobalVerdict`
- Engine collects findings from ALL checks, computes a single drive-level assessment
- Decision rules:
  - SMART failure → always FAILING
  - Failures in 2+ checks → FAILING
  - Single non-SMART failure → AT RISK
  - SMART warning + other warnings → DEGRADING
  - Cross-check conflicts + warnings → DEGRADING
  - Any warnings → WATCH
  - LOW confidence or SMART unknown → UNKNOWN
  - All clear → HEALTHY
- Safety invariants (tested): NEVER returns Healthy with any FAIL finding or LOW confidence
- Cross-check conflict detection: flags when one check says PASS and another says FAIL/WARNING
- Confidence computation: SMART is required for HIGH confidence; single check caps at MEDIUM; SMART LOW → global LOW
- Composite score: SMART weighted 3x, other checks 1x
- Key findings selection: all FAILs + top WARNs
- Human-readable reasoning explains why the verdict was chosen
- Integrated into `run_full_suite()` and `run_macos_full_workflow()`
- Removed ad-hoc "Overall Recommendation" check from macos_full.py — replaced by global verdict
- All stub checks (self-test capability, filesystem macOS stub) now include unified schema keys
- `SuiteResult` carries optional `GlobalVerdict` — serialized in JSON, displayed in CLI
- CLI shows global verdict banner with health/urgency/usage/confidence/score/key findings/conflicts/reasoning
- 47 new tests covering: all healthy, all failing, mixed, conflicts, missing data, confidence downgrade, composite score, key findings selection, determinism, serialization, safety invariants

**Unified health analysis pipeline (Priority 2)**
- Created `checks/evaluate.py` — the single source of truth for verdict determination
  - `compute_score()` — advisory 0-100 score from per-code weights
  - `findings_to_verdict()` — findings list → VerdictResult with verdict, confidence, score, reasoning
  - `verdict_to_check_result()` — VerdictResult → CheckResult with consistent details schema
  - `_build_recommendations()` — severity-based recommendation generation
- Migrated ALL legacy checks to the unified pipeline:
  - `filesystem.py` — produces `fs.mount_not_found`, `fs.write_test_failed`, `fs.fsck_skipped` findings
  - `surface.py` — produces `surface.device_not_found`, `surface.read_errors`, `surface.slow_blocks`, `surface.access_denied` findings
  - `stress.py` — produces `stress.target_not_found`, `stress.io_errors`, `stress.no_ops_completed`, `stress.insufficient_space` findings
  - `integrity.py` — produces `integrity.target_not_found`, `integrity.pattern_mismatch`, `integrity.manifest_mismatch`, `integrity.manifest_missing_files` findings
- Refactored `smart/__init__.py:interpret_smart()` to use shared `verdict_to_check_result()`
  - Removed duplicated recommendation logic and Verdict→Severity mapping
  - SMART error paths (not installed, USB blocked, timeout) also include unified schema keys
- All CheckResult.details now always contain: `verdict`, `confidence`, `health_score`, `findings[]`, `evidence_missing[]`
- No more dual output systems — eliminated the "legacy check" branch in CLI formatter
- Unified CLI output: `_print_findings_banner()` handles ALL check types
  - SMART gets drive identity header; other checks get simpler target header
  - Findings, evidence gaps, and recommendations displayed identically for all checks
- 45 new tests: `test_evaluate.py` (shared pipeline) + `test_unified_checks.py` (migrated checks)
- Cross-check tests verify SMART, filesystem, surface, stress, integrity all conform to identical schema
- Severity consistency verified: PASS↔OK, WARNING↔WARNING, FAIL↔CRITICAL, UNKNOWN↔UNKNOWN everywhere

**Linux disk enumeration (Priority 1)**
- Implemented `_list_disks_linux()` using `lsblk --json --bytes --nodeps` to enumerate physical block devices
- Filters to `type == "disk"` only — skips partitions, loop devices, device-mapper
- Handles `rm` (removable) flag in all forms: bool, int, string
- Normalizes whitespace-only model names to `None`
- `_enrich_linux_mounts()` performs a second `lsblk` call to collect mount points from child partitions
- `list_disks()` now dispatches to Linux when `is_linux` is True
- `_resolve_device()` in CLI now uses `list_disks()` on Linux (not just macOS) — interactive selection works
- `detect` command gives platform-specific error messages when no disks found
- All `lsblk` calls: `text=True`, `check=True`, `timeout=15s`

**Subprocess timeouts (Priority 3 partial)**
- Added 15-second timeout to all `diskutil list -plist` and `diskutil info -plist` calls on macOS
- Added 15-second timeout to all `lsblk` calls on Linux
- Timeout logged as warning and returns empty list (graceful degradation, no hang)

**Tests**
- 16 new tests in `tests/test_linux_disks.py`
- Covers: SATA + NVMe enumeration, USB/removable detection, loop device filtering, mount enrichment from partitions, lsblk not found, non-zero exit, timeout, invalid JSON, size-as-string, null model/tran, whitespace model, rm as int/string, list_disks dispatch to Linux, unsupported platform
- Total: 160 tests passing (up from 144)

### Known limitations (carried forward + updated)
- ~~Linux disk enumeration returns empty~~ → **Fixed**
- ~~Legacy checks bypass findings model~~ → **Fixed** — all checks unified
- ~~No global verdict system~~ → **Fixed** — full aggregation engine with health/urgency/usage/confidence
- NVMe fixtures are synthetic; field names should be verified against a real capture
- `full` command still macOS-only (Linux version not yet designed)
- No Windows disk enumeration
- SMART error paths (smartctl not installed, USB blocked, timeout) construct CheckResult directly — by design since the pipeline requires collected data
- Global verdict `RETIRE` usage level is defined but not yet assigned by any rule (reserved for future SMART self-test failure integration)

### Next steps
- Linux `full` workflow (SMART + self-test recommendation)
- Real NVMe fixture capture and validation
- PyPI packaging
- GUI integration with unified findings and global verdict

---

## v0.1.1 — Safety Fixes (2026-04-10)

### Completed
- Disabled `full` command on non-macOS (was hardcoding mount_point="/")
- Enforced `--allow-destructive` for stress and integrity commands
- Unified GUI service layer to use `collect_and_interpret()`
- Synced version across all doc files
- Fixed `.gitignore` to exclude `dist-*/` and `.venv-*/`

---

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
