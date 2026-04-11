<div align="center">

<br>

<img src="https://img.shields.io/badge/Disk_Health_Checker-0.1.1-22c55e?style=for-the-badge&labelColor=0b0d12" alt="Disk Health Checker"/>

# Disk Health Checker

### Know if your drive is dying — before your data is gone

Reads SMART data from HDDs and SSDs, translates it into a clear health verdict, and tells you exactly what to do next.

<br>

[![Download for macOS](https://img.shields.io/badge/Download-macOS_App-000000?style=for-the-badge&logo=apple&logoColor=white)](https://github.com/quanb24/disk-health-checker/releases/latest)
[![Install with pip](https://img.shields.io/badge/Install-pip_install-3776AB?style=for-the-badge&logo=python&logoColor=white)](#installation)

<br>

![CI](https://github.com/quanb24/disk-health-checker/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11+-3776AB)
![License](https://img.shields.io/badge/license-MIT-22c55e)
![Platform](https://img.shields.io/badge/platform-macOS_·_Linux-8a91a3)
![Tests](https://img.shields.io/badge/tests-252_passing-22c55e)

</div>

<br>

---

## What it does

Most SMART tools dump raw numbers. Disk Health Checker **translates them into a verdict you can act on.**

You run one command. It reads the drive's internal diagnostics, evaluates every signal against tested thresholds, and gives you a **PASS / WARNING / FAIL / UNKNOWN** verdict with a confidence rating, plain-English findings, and next steps.

No raw attribute tables. No googling what "Reallocated_Sector_Ct raw value 6" means. Just: *is this drive safe, and what should I do?*

<br>

---

## Key features

| | |
|---|---|
| **Clear verdicts** | PASS / WARNING / FAIL / UNKNOWN — not raw numbers |
| **Confidence gating** | Won't say "healthy" unless it has enough evidence to prove it |
| **ATA + NVMe** | Supports SATA HDDs, SATA SSDs, and NVMe drives |
| **USB bridge handling** | Automatically retries with SAT passthrough for USB enclosures |
| **Global drive assessment** | Combines SMART, filesystem, and surface checks into one final answer |
| **Beginner-friendly** | `doctor` command explains every finding in plain English |
| **Scriptable** | JSON output with machine-stable finding codes and exit codes |
| **Non-destructive** | All primary commands are read-only — nothing is written to the drive |
| **macOS + Linux** | Disk detection on both platforms (diskutil + lsblk) |
| **GUI included** | PySide6 desktop app with verdict banner, findings list, and next steps |

<br>

---

## How it looks

### CLI output — healthy drive

```
Disk:      Samsung SSD 870 EVO 1TB  (ATA)
           Firmware: SVT02B6Q, Serial: S5Y2NX0R12..., Capacity: 931.5 GB
           Age: ~350 days (8,400 hours)  |  Type: SSD

Verdict:   PASS  (score 100/100, confidence HIGH)

Signals missing: none

Next steps:
  1. No action needed. Keep regular backups as always.
```

### CLI output — drive with warnings

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

### Global verdict — multi-check assessment

```
============================================================

  DRIVE ASSESSMENT:  FAILING

  Urgency:     Replace drive immediately
  Usage:       Do not trust with any data
  Confidence:  HIGH
  Score:       12/100

  Key findings:
    !! [SMART] SMART overall-health self-assessment reports FAILED.
    !! [SurfaceScan] 23 read error(s) during surface scan.

  Overall health: Failing. SMART diagnostics indicate the drive
  is failing. This is the drive's own firmware reporting a
  critical problem.

============================================================
```

<br>

---

## Quick start

<table>
<tr>
<td width="33%" align="center" valign="top">
<h3>1</h3>
<b>Install smartmontools</b><br>
<sub><code>brew install smartmontools</code> (macOS)<br><code>sudo apt install smartmontools</code> (Linux)</sub>
</td>
<td width="33%" align="center" valign="top">
<h3>2</h3>
<b>Install the tool</b><br>
<sub><code>pip install -e .</code> from the repo<br>or download the macOS app</sub>
</td>
<td width="33%" align="center" valign="top">
<h3>3</h3>
<b>Check a drive</b><br>
<sub><code>disk-health-checker smart</code><br>Select a disk and get your verdict</sub>
</td>
</tr>
</table>

<br>

---

## Installation

### macOS

```bash
brew install smartmontools
git clone https://github.com/quanb24/disk-health-checker.git
cd disk-health-checker
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

### Linux (Debian/Ubuntu)

```bash
sudo apt install smartmontools
git clone https://github.com/quanb24/disk-health-checker.git
cd disk-health-checker
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

### macOS App

Download `DiskHealthChecker-0.1.1.dmg` from the [latest release](https://github.com/quanb24/disk-health-checker/releases). Drag to Applications.

> [!NOTE]
> The app is not code-signed. On first launch, right-click the app → **Open** → click **Open** in the dialog. You only need to do this once.

<br>

---

## Usage

### Detect connected disks

```bash
disk-health-checker detect
disk-health-checker detect --verbose
```

### Run SMART diagnostics

```bash
# Interactive disk selection (macOS / Linux)
disk-health-checker smart

# Specify a device directly
disk-health-checker smart --device /dev/disk2         # macOS
disk-health-checker smart --device /dev/sda           # Linux
disk-health-checker smart --device /dev/nvme0n1       # NVMe
```

### Full validation workflow

```bash
disk-health-checker full --device /dev/disk2
```

Runs SMART + self-test capability + filesystem checks, then produces a **global drive assessment** with health level, urgency, recommended usage, and confidence.

### Beginner-friendly explanations

```bash
disk-health-checker doctor --device /dev/disk2
```

Same diagnostics as `smart`, but every finding is rewritten in plain English with practical next steps.

### JSON output

```bash
disk-health-checker --json smart --device /dev/sda
```

> [!TIP]
> Scripts should match on `findings[].code` (e.g. `ata.reallocated.low`), not on message text. Codes are stable across versions.

<br>

---

## Understanding results

### Verdicts

| Verdict | Meaning |
|---------|---------|
| **PASS** | No significant warnings. The drive appears healthy. |
| **WARNING** | Warning signs detected. Usable but should be monitored. |
| **FAIL** | Critical problems. Back up immediately and replace. |
| **UNKNOWN** | Insufficient data. This is **not** the same as "fine." |

The verdict is determined by the **worst finding**, not by the score. A single FAIL finding produces a FAIL verdict even if the score is high.

### Global drive assessment

When running `full`, all checks combine into one final assessment:

| Health | Urgency | Recommended usage |
|--------|---------|-------------------|
| **Healthy** | No action needed | Safe for primary use |
| **Watch** | Monitor over time | Safe for secondary use |
| **Degrading** | Recheck within 30 days | Non-critical storage only |
| **At Risk** | Backup data now | Backup target only |
| **Failing** | Replace drive immediately | Do not trust with any data |
| **Unknown** | Monitor over time | Non-critical storage only |

### Confidence

| Level | Meaning |
|-------|---------|
| **HIGH** | Minimum evidence floor met. Verdict is well-supported. |
| **MEDIUM** | Partial signals. Verdict is defensible but narrower. |
| **LOW** | Below evidence floor. Verdict downgrades to UNKNOWN. |

> [!IMPORTANT]
> A PASS verdict is **never** issued when confidence is LOW. The tool will not claim a drive is healthy when it could not read enough data to verify.

<br>

---

## What it checks

<table>
<tr>
<td width="50%" valign="top">

### ATA / SATA drives

| Signal | What it means |
|--------|---------------|
| Reallocated sectors | Drive moved data from damaged areas |
| Pending sectors | Sectors the drive struggles to read |
| Offline uncorrectable | Data that couldn't be recovered |
| Reported uncorrectable | Read errors visible to the OS |
| UDMA CRC errors | Cable/port problem (not drive failure) |
| Temperature | High temps accelerate wear |
| SSD wear indicator | Write endurance consumed |

</td>
<td width="50%" valign="top">

### NVMe drives

| Signal | What it means |
|--------|---------------|
| Critical warning bits | Hardware alerts from drive firmware |
| Available spare | Reserve blocks for wear leveling |
| Percentage used | Can exceed 100% past rated endurance |
| Media errors | Unrecoverable read errors |
| Temperature | Checked against drive-reported thresholds |

</td>
</tr>
</table>

<br>

---

## Platform support

| Platform | Disk detection | SMART | Status |
|----------|---------------|-------|--------|
| **macOS** (Intel / Apple Silicon) | `diskutil` | `smartctl` | Supported |
| **Linux** | `lsblk` | `smartctl` | Supported |
| **Windows** | — | — | Not supported |

> [!NOTE]
> - Apple Silicon internal storage typically does not expose SMART data — the tool will report UNKNOWN with a clear explanation
> - USB enclosures may block SMART passthrough — the tool retries with `-d sat` automatically and explains the limitation if it fails
> - On Linux, `smartctl` usually requires root — run with `sudo` if needed

<br>

---

## Exit codes

| Code | Verdict | Meaning |
|------|---------|---------|
| `0` | PASS | Drive appears healthy |
| `1` | WARNING | Warning signs detected |
| `2` | FAIL | Critical problems detected |
| `3` | UNKNOWN | Could not determine health |

```bash
disk-health-checker smart --device /dev/sda
case $? in
  0) echo "Drive is healthy" ;;
  1) echo "Drive has warnings" ;;
  2) echo "Drive is failing — back up now" ;;
  3) echo "Could not read SMART data" ;;
esac
```

<br>

---

## Safety

All primary commands (`smart`, `full`, `doctor`, `detect`) are **non-destructive and read-only**. Nothing is written to the drive.

The `stress` and `integrity` commands perform writes in temporary directories and require `--allow-destructive` to run.

<br>

---

## Development

<details>
<summary><b>Build from source · click to expand</b></summary>

<br>

**Requirements:** Python 3.11+, smartmontools

```bash
git clone https://github.com/quanb24/disk-health-checker.git
cd disk-health-checker
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run tests (252 tests)
pytest

# Run with coverage
pytest --cov=disk_health_checker
```

**Architecture:**

```
disk_health_checker/
  checks/          SMART, filesystem, surface, stress, integrity checks
    smart/         ATA + NVMe collection, normalization, evaluation
    evaluate.py    Shared findings → verdict pipeline
  verdict/         Global verdict engine (aggregation across all checks)
  core/            Suite runners (full workflow orchestration)
  models/          Data types (SmartSnapshot, VerdictResult, CheckResult)
  gui/             PySide6 desktop app
  utils/           Platform detection, disk enumeration, I/O helpers
  cli.py           Command-line interface
```

Built with **Python · smartmontools · PySide6 (GUI)**

</details>

<br>

---

## Known limitations

- **Apple Silicon internal storage** does not expose SMART data — this is a macOS/hardware limitation, not a bug
- **Some USB enclosures** block SMART passthrough — the tool retries automatically but some bridges can't be worked around. Try a direct SATA connection or a [SAT-compatible dock](https://sabrent.com/products/ec-dflt)
- **NVMe test fixtures are synthetic** — field names are verified against the spec but not yet against a real drive capture
- **App is not code-signed** — macOS Gatekeeper requires right-click → Open on first launch

<br>

---

## License

MIT — see [LICENSE](./LICENSE).

<br>

---

<div align="center">

## One last thing

Disk Health Checker exists because drives fail silently — and by the time you notice, your data is already gone.

**If this tool saves you from a bad drive, [give it a star](https://github.com/quanb24/disk-health-checker)** — it helps other people find it before it's too late.

<br>

[![Star on GitHub](https://img.shields.io/badge/Star_on_GitHub-f59e0b?style=for-the-badge&labelColor=0b0d12)](https://github.com/quanb24/disk-health-checker)
[![Report an issue](https://img.shields.io/badge/Report_an_issue-ef4444?style=for-the-badge&labelColor=0b0d12)](https://github.com/quanb24/disk-health-checker/issues)
[![Download](https://img.shields.io/badge/Download-22c55e?style=for-the-badge&labelColor=0b0d12)](https://github.com/quanb24/disk-health-checker/releases/latest)

<br>

Made for everyone who has ever lost data to a drive that "seemed fine."

</div>
