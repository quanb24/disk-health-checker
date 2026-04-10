# Release Notes — v0.1.0

## What is Disk Health Checker?

A desktop app and CLI tool that reads SMART data from your hard drives and SSDs, interprets the raw signals into a clear health verdict, and tells you exactly what to do next.

## What's in this release

### Desktop GUI
- Dark-themed PySide6 interface — scan any drive in one click
- Color-coded verdict banner (PASS / WARNING / FAIL / UNKNOWN)
- Sorted findings list with severity cards
- Actionable next-step recommendations
- Progress indicator during scans
- Builds to a standalone macOS `.app` via PyInstaller

### CLI
- `smart` — SMART diagnostics with health scoring
- `full` — non-destructive validation workflow
- `doctor` — beginner-friendly plain-English explanations
- `detect` — list connected disks (macOS)
- `--json` — structured JSON output for scripting
- `--version` — version display
- Exit codes: 0 (PASS), 1 (WARNING), 2 (FAIL), 3 (UNKNOWN)

### SMART Engine
- ATA/SATA: reallocated sectors, pending sectors, offline uncorrectable, reported uncorrectable, UDMA CRC errors, temperature, SSD wear
- NVMe: critical warning bitfield (all 6 bits decoded), available spare, percentage used, media errors, temperature with drive-reported thresholds
- Correct raw-value decoding (temperature low-byte extraction, wear normalized-column-not-raw)
- Confidence gate: never claims PASS without minimum evidence
- Typed exceptions with specific user guidance per failure mode
- USB-SATA bridge auto-retry (`-d sat`) on macOS and Linux

## Platform support

| Platform | CLI | GUI | Disk detection |
|----------|-----|-----|----------------|
| macOS (Intel/Apple Silicon) | Yes | Yes | diskutil |
| Linux | Yes | Yes | Manual (--device) |
| Windows | No | No | — |

## Known limitations

- Linux disk enumeration not automated — requires `--device` flag
- Apple Silicon internal storage typically does not expose SMART data (reports UNKNOWN)
- Some USB enclosures block SMART pass-through
- NVMe fixtures are synthetic — field names verified against spec but not a real drive capture
- Legacy checks (filesystem, surface, stress, integrity) not upgraded to the findings model
- App is not code-signed — macOS Gatekeeper may require right-click > Open on first launch
- No auto-update mechanism

## Requirements

- macOS 13+ or Linux
- Python 3.11+ (for building from source)
- `smartctl` from smartmontools (`brew install smartmontools` / `sudo apt install smartmontools`)

## Test coverage

130 tests across parsing, evaluation, CLI, and output formatting.
