# GUI Architecture Plan

## Framework: PySide6 (Qt for Python)

### Why PySide6

- Same language as the backend — direct function calls, no IPC bridge.
- One process, one runtime. No child process management.
- Native look on macOS and Linux. Professional feel for a diagnostic tool.
- Single-binary packaging via PyInstaller.
- Lowest maintenance burden for a solo developer.

### Alternative: Electron + React

If you prefer web-based UX (you have Electron experience from Fetchwave):
- Backend already supports `--json` output and `interpret_smart()` returns structured data.
- Launch Python as a subprocess from Electron, communicate via JSON over stdout.
- Higher maintenance burden but richer UI possibilities.
- This document focuses on PySide6; the backend API is the same either way.

---

## App structure

```
disk_health_checker/
├── gui/                          # NEW — GUI layer, fully separate from CLI
│   ├── __init__.py
│   ├── app.py                    # QApplication setup, main window launch
│   ├── main_window.py            # MainWindow with layout sections
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── drive_selector.py     # Drive picker (combo box + refresh)
│   │   ├── scan_button.py        # Scan trigger with progress state
│   │   ├── verdict_banner.py     # Large verdict display (PASS/WARN/FAIL/UNKNOWN)
│   │   ├── findings_list.py      # Scrollable findings with severity icons
│   │   └── next_steps_panel.py   # Actionable recommendations
│   └── worker.py                 # QThread worker for background SMART scans
├── cli.py                        # Unchanged
├── checks/smart/                 # Unchanged — GUI calls this directly
└── ...
```

### Entry point

```
pyproject.toml:
[project.gui-scripts]
disk-health-checker-gui = "disk_health_checker.gui.app:main"
```

Also accessible via: `python -m disk_health_checker.gui`

---

## Backend integration

### Direct function calls (no subprocess, no HTTP)

The GUI lives in the same Python process as the backend. It imports and calls
the same functions the CLI uses:

```python
# Drive discovery
from disk_health_checker.utils.disks import list_disks
disks = list_disks()  # -> list[DiskInfo]

# SMART scan
from disk_health_checker.checks.smart.collector import collect_smart
from disk_health_checker.checks.smart.normalize import detect_drive_kind, parse_ata, parse_nvme
from disk_health_checker.checks.smart.ata import evaluate_ata
from disk_health_checker.checks.smart.nvme import evaluate_nvme

result = collect_smart(device)           # -> CollectionResult (raw JSON)
kind = detect_drive_kind(result.data)    # -> DriveKind
if kind == DriveKind.NVME:
    snap = parse_nvme(result.data)       # -> SmartSnapshot
    verdict = evaluate_nvme(snap)        # -> VerdictResult
else:
    snap = parse_ata(result.data)
    verdict = evaluate_ata(snap)

# Or use the high-level wrapper:
from disk_health_checker.checks.smart import interpret_smart
check_result = interpret_smart(result.data)  # -> CheckResult with details dict
```

No new API needed. The backend is already designed for this.

### Threading model

SMART scans can take 1-30 seconds (especially with USB retry and timeout).
The GUI must not block the main thread.

```
MainWindow
  ├── clicks "Scan" button
  ├── disables UI, shows spinner
  ├── starts ScanWorker(QThread)
  │     └── calls collect_smart() + parse + evaluate
  │     └── emits signal with VerdictResult
  ├── receives signal
  ├── updates verdict banner, findings list, next steps
  └── re-enables UI
```

Worker emits typed signals:
- `scan_complete(SmartSnapshot, VerdictResult)` — success
- `scan_error(str)` — typed exception message for display

---

## Screen layout

```
┌──────────────────────────────────────────────────┐
│  disk-health-checker                        v0.1 │
├──────────────────────────────────────────────────┤
│                                                  │
│  Drive: [▾ /dev/disk2 — Samsung 870 EVO 1TB  ]  │  ← DriveSelector
│                                                  │
│  [ Scan Drive ]                                  │  ← ScanButton
│                                                  │
├──────────────────────────────────────────────────┤
│                                                  │
│   ██████████████████████████████████████████████  │
│   ██         PASS — score 100/100           ██  │  ← VerdictBanner
│   ██         confidence: HIGH                ██  │     (color-coded:
│   ██████████████████████████████████████████████  │      green/yellow/
│                                                  │      red/gray)
├──────────────────────────────────────────────────┤
│                                                  │
│  Findings:                                       │  ← FindingsList
│    (none — drive appears healthy)                │
│                                                  │
│  ── or ──                                        │
│                                                  │
│  Findings:                                       │
│   !! Pending sectors: 4 — unstable media         │
│    ! Temperature 58°C — elevated                 │
│                                                  │
├──────────────────────────────────────────────────┤
│                                                  │
│  Next steps:                                     │  ← NextStepsPanel
│   1. Back up data immediately.                   │
│   2. Replace the drive.                          │
│                                                  │
├──────────────────────────────────────────────────┤
│  Signals missing: none                      [?]  │  ← status bar
└──────────────────────────────────────────────────┘
```

---

## How each state is displayed

### PASS
- VerdictBanner: green background, "PASS" in large text
- FindingsList: "No significant warnings detected."
- NextStepsPanel: "No action needed. Keep regular backups."

### WARNING
- VerdictBanner: yellow/amber background, "WARNING"
- FindingsList: each finding with `!` prefix, amber icon
- NextStepsPanel: "Keep backups current. Re-run in 30 days."

### FAIL
- VerdictBanner: red background, "FAIL"
- FindingsList: each finding with `!!` prefix, red icon for FAIL, amber for WARN
- NextStepsPanel: "Back up immediately. Replace the drive."

### UNKNOWN
- VerdictBanner: gray background, "UNKNOWN"
- FindingsList: "Could not read SMART data."
- NextStepsPanel: specific guidance (e.g. "try direct SATA connection")
- Signals missing shown prominently

### Error (smartctl not installed, timeout, etc.)
- VerdictBanner: gray, "ERROR"
- FindingsList: empty
- NextStepsPanel: the exception message rewritten as user guidance
- No fake verdict — the UI clearly says "we could not run the check"

---

## What stays CLI-only

- `--json` output mode
- `--log-level` and `--log-file`
- `--allow-destructive`
- Legacy subcommands (`fs`, `surface`, `stress`, `integrity`)
- Batch/scripting use cases

The GUI exposes only: detect, scan (SMART), and doctor-style explanations.

---

## Packaging

### PySide6 + PyInstaller

```bash
pip install pyinstaller
pyinstaller --onefile --windowed disk_health_checker/gui/app.py
```

Or use a `.spec` file for icon, name, and platform-specific options.

### Dependency addition

```toml
# pyproject.toml
[project.optional-dependencies]
gui = ["PySide6>=6.6"]
dev = ["pytest>=8"]
```

PySide6 is an optional dependency — the CLI works without it.

---

## Implementation order (future sessions)

1. **Minimal window** — app.py + main_window.py with static layout, no scanning
2. **Drive selector** — populate from `list_disks()`, show model/size
3. **Scan worker** — QThread calling `collect_smart` + `parse` + `evaluate`
4. **Verdict banner** — color-coded display from VerdictResult
5. **Findings list** — render findings with severity icons
6. **Next steps panel** — render recommendations
7. **Error handling** — typed exception → user message mapping
8. **Packaging** — PyInstaller config, .app / AppImage generation
9. **Polish** — icons, keyboard shortcuts, menu bar, About dialog
