## disk-health-checker

`disk-health-checker` is a Python CLI tool for evaluating disk health, with a focus on a **safe, macOS-first workflow**.

It provides:

- **Disk detection (macOS)**: Enumerate disks using `diskutil list`.
- **SMART diagnostics**: Query SMART data for a block device (via `smartctl`) and interpret key attributes.
- **Health assessment**: Simple classifications (**HEALTHY**, **WARNING**, **FAILING**) with a 0–100 health score and explanation.
- **Full validation workflow (macOS)**: Non-destructive sequence that checks SMART health, self-test capability, and provides a final recommendation.
- **Legacy checks (non-macOS)**: Filesystem verification, surface scan, stress test, and integrity checks are still available via legacy subcommands.

### Installation on macOS

From the project root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Install smartctl (smartmontools) via Homebrew
brew install smartmontools
```

Ensure that `smartctl` is on your `PATH` after installation (e.g. `which smartctl` should succeed).

### Core macOS commands

- **Detect connected disks**:

```bash
disk-health-checker detect
```

This uses `diskutil list -plist` to show connected disks with size, basic location (internal/external), and model where available.

- **Run SMART diagnostics and health assessment**:

```bash
# Let the tool prompt you to choose a disk (macOS)
disk-health-checker smart

# Or specify a device explicitly
disk-health-checker smart --device /dev/disk2
```

With `--json`, the SMART result and health score are returned as structured JSON:

```bash
disk-health-checker --json smart --device /dev/disk2
```

- **Run a full, non-destructive validation workflow (macOS-first)**:

```bash
# Interactive disk selection on macOS
disk-health-checker full

# Or specify a device explicitly
disk-health-checker full --device /dev/disk2
```

The `full` command:

- Detects/uses the target disk.
- Runs SMART diagnostics and computes a health score.
- Checks for SMART self-test capability and recommends a long self-test when possible.
- Provides a macOS filesystem verification stub (`diskutil verifyVolume` guidance).
- Produces a final recommendation: **SAFE TO USE**, **USE WITH CAUTION**, or **DO NOT TRUST**.

- **Explain SMART results in beginner-friendly language**:

```bash
disk-health-checker doctor          # choose a disk interactively on macOS
disk-health-checker doctor --device /dev/disk2
```

The `doctor` command:

- Runs SMART diagnostics.
- Explains any warnings (reallocated sectors, pending sectors, uncorrectable errors, high temperature, SSD wear).
- Suggests clear next steps (e.g. keep backups, replace the drive, improve cooling, avoid critical use).

### Legacy / advanced commands

On platforms other than macOS, or for deeper diagnostics, the following subcommands remain available:

- `fs` – filesystem verification
- `surface` – disk surface scan
- `stress` – read/write stress test
- `integrity` – data integrity verification

See `disk-health-checker --help` for full details and options.

### Safety

By default, `disk-health-checker` is **non-destructive**:

- SMART operations are read-only.
- The macOS-first `full` workflow does **not** perform destructive writes.
- Advanced write tests (stress/integrity) operate in temporary directories and avoid consuming more than a small fraction of free space, and are not enabled by default.

Always ensure you have backups of important data and understand the implications of running any disk diagnostic tools on production systems.

