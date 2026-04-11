# Validation Notes

**Date:** 2026-04-10
**Drive:** WD My Book 6 TB (model EDAZ-11BMZB0)
**Connection:** USB (external enclosure)
**Filesystem:** exFAT
**Mount point:** /Volumes/My Book
**Volume device:** /dev/disk4s1
**Parent whole disk:** /dev/disk4
**Host:** macOS 14.2.1 (Darwin 23.2.0), Apple Silicon

## Key observations

1. **SMART is completely blocked by the USB enclosure.**
   - diskutil reports "SMART Status: Not Supported"
   - smartctl cannot open the device at all ("Operation not supported by device")
   - macOS kernel does not expose it as a SCSI target, so SAT passthrough is impossible
   - All 6 fallback modes (auto, sat, sat12, sat16, usbsunplus, usbjmicron) failed

2. **system_profiler says "S.M.A.R.T. status: Verified" — this is misleading.**
   - This value comes from the enclosure firmware reporting itself as healthy
   - It does NOT reflect actual SMART telemetry from the drive platters
   - The WD My Book enclosure has its own firmware that responds to USB health queries
   - This should NOT be interpreted as "SMART passed"

3. **Filesystem check passed.**
   - The tool successfully created and deleted a temp file on /Volumes/My Book
   - Read/write works, permissions are normal
   - Drive is nearly empty: 94 MB used on 6 TB (0.0%)

4. **Drive identification:**
   - Model: WD60 EDAZ-11BMZB0 (from ioreg)
   - This is a WD Blue 6TB 5400RPM HDD (WD60EZAZ variant in a My Book enclosure)
   - The "EDAZ" prefix is the internal WD model; "My Book" is the retail product name

5. **The drive is almost certainly a new/recently formatted drive.**
   - Only 94 MB used on 6 TB — essentially empty
   - exFAT formatting suggests it was set up for cross-platform use

## What was NOT tested

- SMART health, power-on hours, reallocated sectors, temperature, wear
- Surface scan (would require reading raw blocks from /dev/disk4)
- Stress test (destructive, not requested)
- Integrity test (destructive, not requested)
- SMART self-test (requires SMART access, which is blocked)
