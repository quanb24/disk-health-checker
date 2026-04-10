# disk-health-checker

[![CI](https://github.com/quanb24/disk-health-checker/actions/workflows/ci.yml/badge.svg)](https://github.com/quanb24/disk-health-checker/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

A desktop app and CLI tool that reads SMART data from HDDs and SSDs, interprets it into a human-readable health verdict, and tells you what to do next.

Instead of dumping raw SMART attributes, `disk-health-checker` translates them into **PASS / WARNING / FAIL / UNKNOWN** with plain-English findings, a confidence rating, and actionable next steps.

Supports **ATA/SATA** and **NVMe** drives on **macOS** and **Linux**. Available as a GUI app or command-line tool.

## Download

**macOS:** Download `DiskHealthChecker-0.1.1.dmg` from the [latest release](https://github.com/quanb24/disk-health-checker/releases). Open the DMG and drag to Applications.

> **Note:** The app is not code-signed. On first launch, right-click the app and select Open, then click Open in the dialog.

**Build from source:** See [BUILD.md](BUILD.md) for step-by-step instructions.

**Requirements:** `smartctl` must be installed — `brew install smartmontools` (macOS) or `sudo apt install smartmontools` (Linux).

## Example output

```
Disk:      WD Blue 1TB HDD  (ATA)
           Firmware: 80.00A80, Serial: WD-WCAZ123..., Capacity: 931.5 GB
           Age: ~4.8 years (42,000 hours)  |  Type: HDD

Verdict:   WARNING  (score 70/100, confidence HIGH)

Why:
  ! 6 reallocated sector(s) — small reallocation, monitor trend.
  ! Drive temperature 58 °C — elevated, consider improving airflow.

Signals missing: none

Next steps:
  1. Keep backups current. This drive is usable but has warning signs.
  2. Re-run this check in ~30 days to monitor for progression.
```

When the drive is healthy:

```
Disk:      Samsung SSD 870 EVO 1TB  (ATA)
           Firmware: SVT02B6Q, Serial: S5Y2NX0R12..., Capacity: 931.5 GB
           Age: ~350 days (8,400 hours)  |  Type: SSD

Verdict:   PASS  (score 100/100, confidence HIGH)

Signals missing: none

Next steps:
  1. No action needed. Keep regular backups as always.
```

When SMART data is unavailable (e.g. behind a USB enclosure):

```
Verdict:   UNKNOWN  (confidence LOW)

Signals missing: smart_status.passed, pending_sectors, offline_uncorrectable,
                 reallocated_sectors, temperature_c

Next steps:
  1. Could not determine drive health. See signals missing above.
```

## Installation

### Requirements

- Python 3.11 or later
- `smartctl` from [smartmontools](https://www.smartmontools.org/)

### macOS

```bash
# Install smartmontools
brew install smartmontools

# Clone and install
git clone https://github.com/quanb24/disk-health-checker.git
cd disk-health-checker
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Linux (Debian/Ubuntu)

```bash
# Install smartmontools
sudo apt install smartmontools

# Clone and install
git clone https://github.com/quanb24/disk-health-checker.git
cd disk-health-checker
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Verify installation

```bash
which smartctl          # should print a path
disk-health-checker --help
```

## Usage

### Detect connected disks (macOS)

```bash
disk-health-checker detect
disk-health-checker detect --verbose
```

### Run SMART diagnostics

```bash
# macOS: interactive disk selection
disk-health-checker smart

# Specify a device explicitly (macOS or Linux)
disk-health-checker smart --device /dev/disk2       # macOS
disk-health-checker smart --device /dev/sda          # Linux
disk-health-checker smart --device /dev/nvme0n1      # Linux NVMe
```

### Run a full validation workflow

```bash
# macOS: SMART + self-test capability check + filesystem guidance
disk-health-checker full --device /dev/disk2

# Linux: SMART + legacy checks
disk-health-checker full --device /dev/sda
```

The `full` command is non-destructive. It analyzes, classifies, and recommends — it does not run long self-tests or write to the drive.

### Get beginner-friendly explanations

```bash
disk-health-checker doctor --device /dev/disk2
```

The `doctor` command runs the same diagnostics as `smart` but rewrites every finding into plain English with practical guidance.

### JSON output

```bash
disk-health-checker --json smart --device /dev/sda
```

JSON output includes structured fields for scripting:

```json
{
  "check_results": [{
    "details": {
      "verdict": "WARNING",
      "confidence": "HIGH",
      "health_score": 85,
      "findings": [
        {
          "code": "ata.reallocated.low",
          "severity": "WARN",
          "message": "6 reallocated sector(s) — small reallocation, monitor trend.",
          "evidence": {"count": 6}
        }
      ],
      "evidence_missing": [],
      "device_kind": "ata",
      "model_name": "Samsung SSD 870 EVO 1TB"
    }
  }]
}
```

Scripts should match on `findings[].code`, not on message text.

## How to interpret results

### Verdicts

| Verdict | Meaning |
|---------|---------|
| **PASS** | No significant warnings detected. The drive appears healthy based on available SMART data. |
| **WARNING** | One or more warning-level findings. The drive is usable but should be monitored. |
| **FAIL** | One or more critical findings. Back up immediately and plan for replacement. |
| **UNKNOWN** | Insufficient SMART data to make a determination. This is not the same as "the drive is fine." |

The verdict is determined by the **worst finding**, not by the score. A single FAIL finding produces a FAIL verdict even if the score is high.

### Confidence

| Level | Meaning |
|-------|---------|
| **HIGH** | The minimum evidence floor was met. The verdict is well-supported. |
| **MEDIUM** | Partial signals available. The verdict is defensible but narrower. |
| **LOW** | Below the minimum evidence floor. Verdict downgrades to UNKNOWN. |

**Minimum evidence floor:**

- ATA: `smart_status.passed` present AND at least one of {reallocated sectors, pending sectors, offline uncorrectable} readable.
- NVMe: `critical_warning` present AND `available_spare` present.

A PASS verdict is never issued when the confidence is LOW. The tool will not claim a drive is healthy when it could not read enough data to verify.

### Health score (0–100)

The score is advisory. It provides a rough sense of distance from ideal, but the verdict is authoritative. Do not use the score as a substitute for reading the findings.

### What the tool checks

**ATA/SATA drives:**

| Signal | What it means |
|--------|---------------|
| Reallocated sectors | Drive moved data away from damaged areas. Small counts are common; rapid growth is a warning. |
| Pending sectors | Sectors the drive is struggling to read. Strong predictor of failure. |
| Offline uncorrectable | Data that could not be recovered even with error correction. |
| Reported uncorrectable | Read errors visible to the operating system. |
| UDMA CRC errors | Usually a cable or port problem, not drive failure. |
| Temperature | High temperatures accelerate wear. |
| SSD wear indicator | How much of the drive's rated write endurance has been consumed. |

**NVMe drives:**

| Signal | What it means |
|--------|---------------|
| Critical warning bits | Drive-reported hardware alerts (spare below threshold, reliability degraded, read-only mode, temperature, backup failure). |
| Available spare | Remaining reserve blocks for wear leveling. |
| Percentage used | Can exceed 100% — the drive may still work past rated endurance. |
| Media errors | Unrecoverable read errors (uncommon on NVMe). |
| Temperature | Checked against drive-reported thresholds when available. |

### Finding codes

Findings use machine-stable codes for scripting. Examples:

- `ata.pending_sectors` — pending sectors detected (FAIL)
- `ata.reallocated.low` — small reallocation count (WARN)
- `ata.reallocated.high` — high reallocation count (FAIL)
- `ata.temperature.elevated` — temperature 55–64 °C (WARN)
- `nvme.critical_warning.reliability_degraded` — NVM subsystem reliability degraded (FAIL)
- `nvme.wear_past_endurance` — percentage_used >= 100% (WARN)
- `nvme.spare_below_threshold` — available spare at or below threshold (FAIL)

## Platform support

| Platform | Disk detection | SMART diagnostics | Status |
|----------|---------------|-------------------|--------|
| macOS (Intel/Apple Silicon) | diskutil | smartctl | Supported |
| Linux | Manual (`--device`) | smartctl | Supported |
| Windows | — | — | Not supported |

**Notes:**

- Apple Silicon internal storage (APFS synthesis) typically does not expose SMART data. The tool will report UNKNOWN with a clear explanation.
- Some USB enclosures block SMART pass-through. The tool retries with `-d sat` automatically and provides guidance if it still fails.
- On Linux, `smartctl` usually requires root. Run with `sudo` if you get permission errors.

## Exit codes

| Code | Verdict | Use in scripts |
|------|---------|----------------|
| 0 | PASS | Drive appears healthy |
| 1 | WARNING | Warning signs detected |
| 2 | FAIL | Critical problems detected |
| 3 | UNKNOWN | Could not determine health |

Example:

```bash
disk-health-checker smart --device /dev/sda
case $? in
  0) echo "Drive is healthy" ;;
  1) echo "Drive has warnings — check output" ;;
  2) echo "Drive is failing — back up now" ;;
  3) echo "Could not read SMART data" ;;
esac
```

## Legacy commands

For deeper diagnostics, these subcommands are available but are not part of the primary SMART workflow:

- `fs` — filesystem verification
- `surface` — read-only surface scan
- `stress` — read/write stress test
- `integrity` — data integrity verification

See `disk-health-checker --help` for options.

## Safety

All primary commands (`smart`, `full`, `doctor`, `detect`) are **non-destructive** and read-only. SMART operations do not write to the drive.

The legacy `stress` and `integrity` commands perform writes in temporary directories and are not enabled by default. Use `--allow-destructive` to enable them.

## Known limitations

- **Apple Silicon internal storage** does not expose SMART data — the tool will report UNKNOWN. This is a macOS/hardware limitation, not a bug.
- **Some USB enclosures** block SMART pass-through. The tool retries with `-d sat` automatically, but some bridges cannot be worked around. Try a direct SATA connection.
- **Linux disk detection** is not automated — use `--device /dev/sdX` explicitly.
- **App is not code-signed** — macOS Gatekeeper requires right-click > Open on first launch.
- **NVMe test fixtures are synthetic** — field names are verified against the NVMe spec but not a real drive capture yet.

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=disk_health_checker
```

## License

MIT
