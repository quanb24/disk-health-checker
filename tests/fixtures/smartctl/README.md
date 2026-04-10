# SMART Test Fixtures

Files ending in `.synthetic.json` are **hand-crafted** from spec documentation
and smartmontools source — they are NOT captures from real hardware.

Synthetic fixtures are built from:
- NVMe Base Specification 1.4, Section 5.14.1.2 (SMART / Health Information Log)
- smartmontools JSON output documentation (smartctl -j)

When a real drive capture is available, add it as `<name>.real.json` with the
serial number scrubbed. Update tests to cover both synthetic and real fixtures.
