# QA Checklist — v0.1.0

Manual verification checklist. Test each item against the built `.app`.

## GUI — App Launch

- [ ] App opens without crash
- [ ] Window title shows "Disk Health Checker v0.1.0"
- [ ] Dark theme renders (not white/unstyled)
- [ ] Header bar shows app name and version

## GUI — Drive Selection

- [ ] Drive dropdown populates on launch
- [ ] Drives show device path, model, and size
- [ ] Refresh button repopulates the list
- [ ] "No disks detected" message if no drives found

## GUI — Scan Flow

- [ ] Scan button is clickable
- [ ] Clicking Scan disables the button and drive selector
- [ ] Progress bar appears during scan
- [ ] "Scanning..." text shows in verdict banner with device path
- [ ] Scan completes and re-enables controls

## GUI — Verdict Display

- [ ] PASS: green banner, "Drive appears healthy"
- [ ] WARNING: amber banner, warning description shown
- [ ] FAIL: red banner, "Critical problems — take action now"
- [ ] UNKNOWN: gray banner, "NOT the same as healthy" text visible
- [ ] Score shows (e.g. "85/100")
- [ ] Confidence shows (HIGH / MEDIUM / LOW)
- [ ] Drive info line shows model, type, age, temperature

## GUI — Findings

- [ ] Findings appear as cards with severity badges (FAIL / WARN)
- [ ] FAIL findings appear before WARN findings
- [ ] Each finding has a readable message
- [ ] "No significant warnings detected" shown when PASS
- [ ] Missing signals shown as GAP card when relevant

## GUI — Next Steps

- [ ] Recommendations appear after scan
- [ ] FAIL: first step is bold red ("Back up all data...")
- [ ] WARNING: actionable monitoring guidance
- [ ] PASS: "No action needed"

## GUI — Error Handling

- [ ] Error when smartctl not installed: clear message, not crash
- [ ] Error when device not accessible: clear message
- [ ] Error banner shows ERR badge in findings area
- [ ] Next steps panel shows recovery guidance

## CLI

- [ ] `disk-health-checker --version` prints `disk-health-checker 0.1.0`
- [ ] `disk-health-checker --help` prints usage
- [ ] `disk-health-checker smart --device /dev/disk0` runs (may need sudo)
- [ ] `disk-health-checker --json smart --device /dev/disk0` outputs valid JSON
- [ ] `disk-health-checker doctor --device /dev/disk0` runs
- [ ] `disk-health-checker detect` lists drives
- [ ] Exit code 0/1/2/3 matches PASS/WARNING/FAIL/UNKNOWN

## Packaging

- [ ] `.app` launches from `dist/` directory
- [ ] `.app` launches from mounted `.dmg`
- [ ] No console/terminal window appears with `.app`
- [ ] App works after dragging to Applications folder
