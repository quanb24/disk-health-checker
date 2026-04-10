# Disk Health Checker — Complete Tutorial

Step-by-step guide to install, run, and use Disk Health Checker on macOS.

---

## Part 1: Installation

### Step 1 — Install smartmontools

The tool needs `smartctl` to read SMART data from your drives. Install it via Homebrew:

```bash
brew install smartmontools
```

Verify it installed:

```bash
smartctl --version
```

You should see something like `smartctl 7.4 ...`. If you get "command not found", Homebrew may not be in your PATH — try restarting your terminal.

### Step 2 — Clone the repository

```bash
cd ~/Desktop
git clone https://github.com/quanb24/disk-health-checker.git
cd disk-health-checker
```

### Step 3 — Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now show `(.venv)` at the beginning. Every time you open a new terminal to use this tool, you'll need to run:

```bash
cd ~/Desktop/disk-health-checker
source .venv/bin/activate
```

### Step 4 — Install the tool

```bash
pip install -e ".[gui]"
```

This installs:
- The CLI tool (`disk-health-checker` command)
- The GUI app (PySide6)
- All backend dependencies

### Step 5 — Verify installation

```bash
disk-health-checker --version
```

Expected output: `disk-health-checker 0.1.0`

```bash
disk-health-checker --help
```

You should see the list of commands (detect, smart, full, doctor, etc.).

---

## Part 2: Using the CLI

### Find your drives

```bash
disk-health-checker detect
```

This lists all connected drives with their device paths, sizes, and locations (internal/external). Example output:

```
Detected disks:
- /dev/disk0: 465.9 GB, internal, mounts: /
- /dev/disk4: 931.5 GB, external, mounts: /Volumes/MyDrive
```

For more detail (model, bus protocol):

```bash
disk-health-checker detect --verbose
```

**Write down the device path** (e.g. `/dev/disk0`, `/dev/disk4`) of the drive you want to check.

### Run a SMART scan

```bash
disk-health-checker smart --device /dev/disk4
```

Replace `/dev/disk4` with your actual device path.

Example output:

```
Disk:      Samsung SSD 870 EVO 1TB  (ATA)
           Firmware: SVT02B6Q, Serial: S5Y2NX0R12..., Capacity: 931.5 GB
           Age: ~350 days (8,400 hours)  |  Type: SSD

Verdict:   PASS  (score 100/100, confidence HIGH)

Signals missing: none

Next steps:
  1. No action needed. Keep regular backups as always.
```

### Run a SMART scan and SAVE the results

This is how you capture results to share with me:

```bash
disk-health-checker --json smart --device /dev/disk4 > ~/Desktop/disk4_results.json
```

This saves the full structured results to a file on your Desktop.

**To save results for EVERY drive**, run it for each one:

```bash
# First, see what drives you have
disk-health-checker detect

# Then scan each one and save results
disk-health-checker --json smart --device /dev/disk0 > ~/Desktop/disk0_results.json
disk-health-checker --json smart --device /dev/disk4 > ~/Desktop/disk4_results.json
```

Each file contains:
- verdict (PASS / WARNING / FAIL / UNKNOWN)
- confidence level
- health score
- every finding with severity and evidence
- all raw SMART values
- what signals were missing

### Get beginner-friendly explanations

```bash
disk-health-checker doctor --device /dev/disk4
```

Same scan, but findings are explained in plain English with practical advice.

### Run the full validation workflow

```bash
disk-health-checker full --device /dev/disk4
```

This runs SMART diagnostics + checks self-test capability + provides a final recommendation (SAFE TO USE / USE WITH CAUTION / DO NOT TRUST).

### Save full workflow results

```bash
disk-health-checker --json full --device /dev/disk4 > ~/Desktop/disk4_full.json
```

---

## Part 3: Using the GUI

### Launch the GUI

```bash
python3 -m disk_health_checker.gui
```

Or if you built the `.app`:

```bash
open "dist/Disk Health Checker.app"
```

### Using the GUI

1. **Select a drive** — The dropdown at the top shows all detected drives. Pick the one you want to check.
2. **Click "Scan Drive"** — A progress bar appears while it reads SMART data.
3. **Read the verdict** — The large colored banner shows PASS (green), WARNING (amber), FAIL (red), or UNKNOWN (gray).
4. **Review findings** — Each finding is a card showing what was detected and why it matters.
5. **Follow next steps** — Actionable recommendations based on the verdict.

### What the colors mean

| Color | Verdict | What to do |
|-------|---------|------------|
| Green | PASS | Drive looks healthy. Keep backups as always. |
| Amber | WARNING | Warning signs found. Keep backups current, re-check in 30 days. |
| Red | FAIL | Critical problems. Back up immediately, plan to replace the drive. |
| Gray | UNKNOWN | Could not read SMART data. Do not assume the drive is healthy. |

---

## Part 4: Saving and Sharing Results

### Save CLI results to a file

```bash
# Basic SMART scan — saves everything
disk-health-checker --json smart --device /dev/disk4 > ~/Desktop/results.json

# Full workflow — saves even more detail
disk-health-checker --json full --device /dev/disk4 > ~/Desktop/results_full.json
```

### What's inside the JSON file

The saved JSON includes:
- `verdict`: PASS / WARNING / FAIL / UNKNOWN
- `confidence`: HIGH / MEDIUM / LOW
- `health_score`: 0-100
- `findings`: list of every issue found, with severity and evidence
- `evidence_missing`: what the tool couldn't read
- `model_name`, `serial_number`, `firmware_version`
- `reallocated_sectors`, `pending_sectors`, `temperature_c`, etc.
- `power_on_hours`: how long the drive has been running
- All raw SMART attribute values

### Quick-read the results without opening the file

```bash
# Just see the verdict
cat ~/Desktop/results.json | python3 -c "import json,sys; d=json.load(sys.stdin)['check_results'][0]['details']; print(f'Verdict: {d[\"verdict\"]} | Score: {d[\"health_score\"]}/100 | Confidence: {d[\"confidence\"]}')"
```

### Share results for analysis

To share results with someone for analysis, send them:
1. The `.json` file(s) from `~/Desktop/`
2. Which drive it was (internal SSD, external HDD, etc.)
3. What problem you're investigating (if any)

The JSON contains the serial number (partially). If privacy matters, you can scrub it:

```bash
# Remove serial before sharing
cat ~/Desktop/results.json | python3 -c "
import json, sys
d = json.load(sys.stdin)
for cr in d.get('check_results', []):
    details = cr.get('details', {})
    if 'serial_number' in details:
        details['serial_number'] = 'REDACTED'
json.dump(d, sys.stdout, indent=2)
" > ~/Desktop/results_safe.json
```

---

## Part 5: Testing All Your Drives (Recommended First Use)

Run this to scan every drive and save all results in one shot:

```bash
# Create a results folder
mkdir -p ~/Desktop/disk-health-results

# Detect drives and save the list
disk-health-checker detect --verbose > ~/Desktop/disk-health-results/drives.txt
cat ~/Desktop/disk-health-results/drives.txt

# Scan each drive (replace device paths with yours from the detect output)
# Example for a system with disk0 (internal) and disk4 (external):

disk-health-checker --json smart --device /dev/disk0 > ~/Desktop/disk-health-results/disk0.json 2>&1
echo "disk0: exit code $?"

disk-health-checker --json smart --device /dev/disk4 > ~/Desktop/disk-health-results/disk4.json 2>&1
echo "disk4: exit code $?"

# Quick summary of all results
echo "=== Results Summary ==="
for f in ~/Desktop/disk-health-results/disk*.json; do
  name=$(basename "$f" .json)
  verdict=$(python3 -c "import json; d=json.load(open('$f')); print(d['check_results'][0]['details'].get('verdict','ERROR'))" 2>/dev/null || echo "PARSE_ERROR")
  score=$(python3 -c "import json; d=json.load(open('$f')); print(d['check_results'][0]['details'].get('health_score','?'))" 2>/dev/null || echo "?")
  echo "  $name: $verdict (score $score/100)"
done
```

### Exit codes for scripting

| Exit Code | Meaning |
|-----------|---------|
| 0 | PASS — drive appears healthy |
| 1 | WARNING — warning signs detected |
| 2 | FAIL — critical problems |
| 3 | UNKNOWN — could not read SMART data |

---

## Part 6: Troubleshooting

### "smartctl not found"

```bash
brew install smartmontools
```

### "SMART not available for this device"

The drive is behind a USB enclosure that blocks SMART data. The tool automatically retries with `-d sat`, but some enclosures can't be worked around. Try:
- Connecting the drive directly via SATA
- Using a different USB enclosure

### "UNKNOWN" verdict on internal Mac drive

Apple Silicon Macs don't expose SMART data for the internal SSD through smartctl. This is a hardware/OS limitation, not a bug. The tool correctly reports UNKNOWN rather than guessing.

### Permission denied

On Linux, smartctl usually needs root:

```bash
sudo disk-health-checker smart --device /dev/sda
```

On macOS, most external drives work without sudo. Internal drives may require it.

### GUI won't launch

Make sure you installed the GUI dependencies:

```bash
pip install -e ".[gui]"
```

If you get an error about PySide6, try:

```bash
pip install PySide6
```

---

## Quick Reference

| Task | Command |
|------|---------|
| List drives | `disk-health-checker detect` |
| Scan a drive | `disk-health-checker smart --device /dev/diskX` |
| Scan and save | `disk-health-checker --json smart --device /dev/diskX > results.json` |
| Full check | `disk-health-checker full --device /dev/diskX` |
| Plain English | `disk-health-checker doctor --device /dev/diskX` |
| Launch GUI | `python3 -m disk_health_checker.gui` |
| Version | `disk-health-checker --version` |
