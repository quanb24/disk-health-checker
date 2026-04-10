# Release Notes — v0.1.1

## What's new in v0.1.1

### Improved external USB drive handling

- **Smarter USB bridge fallback chain** — when an external drive blocks SMART, the tool now tries multiple passthrough modes (SAT, SAT-12, SAT-16, Sunplus, JMicron) before giving up. Early exit when the OS confirms the device can't support SCSI-based passthrough.
- **New `UsbBridgeBlocked` error classification** — clearly distinguishes "USB enclosure blocking SMART" from "drive failing", "permission denied", "smartctl missing", or "timeout". Each failure type now carries a `failure_reason` in the output.
- **Better CLI output** — when a USB enclosure blocks SMART, the CLI now explains what happened, why, and what the user can do (connect via direct SATA, use a SAT-compatible dock, etc.) instead of a generic "SMART check unavailable".
- **Better GUI output** — USB-blocked drives show an amber informational state (not alarming red), with a clear explanation that the enclosure is the barrier, not the drive. Actionable next steps are provided.
- **Transport-aware scanning** — disk enumeration protocol (USB, SATA, NVMe) is now passed to the SMART collector, enabling smarter retry decisions.
- **14 new tests** for USB bridge fallback, early stop, chain exhaustion, success recording, and no-regression on internal drives. Test count: 144 (was 130).

### What this does NOT do

- Does not bypass hardware that blocks SMART — if the USB bridge drops all commands, no software can read health data.
- Does not fake a PASS verdict — UNKNOWN remains honest when evidence is missing.

---

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
