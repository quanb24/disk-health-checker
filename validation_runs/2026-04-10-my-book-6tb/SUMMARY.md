# Validation Summary

**Drive:** WD My Book 6 TB (WD60 EDAZ-11BMZB0)
**Date:** 2026-04-10T20:18 EDT
**Connection:** USB external enclosure
**Tool version:** disk-health-checker 0.1.1

---

## 1. Device mapping

| Property | Value |
|---|---|
| Volume | /dev/disk4s1 (My Book, exFAT) |
| Parent disk | /dev/disk4 (whole disk) |
| Mount point | /Volumes/My Book |
| Protocol | USB |
| Location | External |
| Removable media | No (fixed in enclosure) |
| Drive model | WD60 EDAZ-11BMZB0 (WD Blue 6TB 5400RPM) |

## 2. Commands run

| Command | Result |
|---|---|
| `diskutil info "/Volumes/My Book"` | Success — confirmed device mapping |
| `diskutil info /dev/disk4` | Success — confirmed parent disk, USB, SMART Not Supported |
| `system_profiler SPUSBDataType` | Success — identified enclosure, misleading SMART "Verified" |
| `ioreg` | Success — confirmed internal WD model name |
| `smartctl -i -j /dev/disk4` | Failed — "Operation not supported by device" |
| `smartctl -i -j -d sat /dev/disk4` | Failed — "Not a device of type 'scsi'" |
| `disk-health-checker detect` | Success — correctly listed drive as /dev/disk4, external, USB |
| `disk-health-checker smart --device /dev/disk4` | UNKNOWN — USB bridge blocked all SMART access |
| `disk-health-checker doctor --device /dev/disk4` | UNKNOWN — same root cause |
| `disk-health-checker fs --mount "/Volumes/My Book"` | PASS — filesystem writable, 100/100 |
| `disk-health-checker full --device /dev/disk4` | UNKNOWN — global verdict correctly reports low confidence |

## 3. Important raw findings

- **SMART is completely inaccessible.** The macOS kernel does not expose
  this USB device as a SCSI target, so smartctl cannot communicate with
  the drive at all. All 6 fallback modes failed. This is not a tool
  limitation — it is a hardware limitation of the WD My Book enclosure.

- **system_profiler reports "S.M.A.R.T. status: Verified" but this is
  the enclosure firmware talking, not actual SMART data.** The enclosure
  responds to USB health queries with "I'm fine" regardless of what the
  actual drive platters think. This value should be ignored.

- **Filesystem check passed.** The drive is mounted, writable, and the
  tool confirmed it can create and read back files. The volume is nearly
  empty (94 MB / 6 TB).

## 4. disk-health-checker verdict

```
DRIVE ASSESSMENT:  UNKNOWN
Urgency:     Monitor over time
Usage:       Non-critical storage only
Confidence:  LOW
Score:       80/100
```

The tool correctly identified that SMART data is unavailable and set
confidence to LOW. It did NOT claim the drive is healthy.

## 5. Confidence level and why

**Confidence: LOW** — this is correct and appropriate.

The tool had access to:
- Filesystem: PASS (high confidence for this check)
- SMART: UNKNOWN (zero data — USB bridge blocked everything)
- Self-test: UNKNOWN (requires SMART access)
- Surface scan: not run
- Stress/integrity: not run (destructive)

Without SMART, we cannot assess:
- Reallocated sectors (early sign of media degradation)
- Pending sectors (active read failures)
- Power-on hours (drive age)
- Temperature (thermal stress)
- Overall health self-assessment (drive's own firmware opinion)

The score of 80/100 comes from the composite scoring (SMART unknown gets
a reduced score, filesystem passed). This is reasonable but should not
be interpreted as "80% healthy." It means "we have 80% of an answer,
and the 20% we're missing is the most important part."

## 6. Whether USB limited visibility

**Yes, severely.** The USB enclosure completely blocks all SMART access.
This is the #1 limitation of this validation. We can confirm the drive
mounts, reads, and writes, but we cannot see any internal health data.

The WD My Book uses a proprietary USB-SATA bridge that does not support
SAT (SCSI-ATA Translation) passthrough. This is common in consumer WD
external drives. The macOS kernel makes it worse by not even exposing
the device as a SCSI target.

## 7. Whether the drive looks okay

**Uncertain — not concerning, but genuinely unknown.**

What we know:
- The drive mounts and is accessible
- Filesystem operations work correctly
- The volume appears to be freshly formatted (almost empty)
- No I/O errors observed during the filesystem test
- No macOS Console errors observed

What we don't know:
- Whether the drive has any reallocated/pending sectors
- How many power-on hours (could be brand new or 5 years old)
- Drive temperature
- Whether the drive's own firmware considers itself healthy

**Conservative assessment:** The drive is usable for secondary/backup
storage, but it should not be the sole copy of important data until
SMART health can be verified. There is no evidence of problems, but
there is also no evidence of health.

## 8. Files created

```
validation_runs/2026-04-10-my-book-6tb/
  01-diskutil-volume.txt        diskutil info for the volume
  02-diskutil-parent-disk.txt   diskutil info for /dev/disk4
  03-system-profiler-usb.txt    USB device details + SMART discrepancy note
  04-smartctl-attempts.txt      All failed smartctl attempts documented
  05-smart-check.json           disk-health-checker SMART output (JSON)
  06-filesystem-check.json      disk-health-checker filesystem output (JSON)
  07-full-workflow.json          disk-health-checker full workflow (JSON)
  08-detect.txt                 disk-health-checker detect output
  NOTES.md                      Detailed observation notes
  SUMMARY.md                    This file
```

## 9. Recommended next step

**To get a real health assessment, remove the drive from the WD My Book
enclosure and connect it directly via SATA or a known-good SAT dock.**

Specific options:
1. **Best:** Open the My Book enclosure, extract the WD Blue 6TB drive,
   connect via SATA to a desktop motherboard, then run
   `disk-health-checker smart --device /dev/sdX` (Linux) or equivalent.
2. **Good:** Use a USB dock known to support SAT passthrough (Sabrent,
   StarTech, some Anker models). Not all docks work — the dock must
   have a bridge chip that supports SCSI-ATA Translation.
3. **If you can't open it:** Use the drive for non-critical storage only
   and monitor for obvious signs of failure (slow reads, clicking sounds,
   I/O errors in Console.app). Run `diskutil verifyVolume disk4s1`
   periodically.

---

## Second-pass audit

### Potential misleading signals

1. **system_profiler "S.M.A.R.T. status: Verified"** — This is the most
   dangerous misleading signal. A user who sees this might think the drive
   passed SMART. It did not. The enclosure firmware is answering, not the
   drive. This is called out in the notes but should be flagged more
   prominently in future tool output.

2. **Composite score 80/100** — This could be misread as "the drive is
   80% healthy." It actually means "we completed 80% of a possible
   assessment." The most important 20% (SMART) is missing. The tool
   should consider displaying this differently in UNKNOWN scenarios.

3. **Filesystem PASS** — This is real and trustworthy, but it only proves
   the filesystem layer works. A drive with 50,000 reallocated sectors
   would still pass a filesystem write test as long as the remaining
   sectors work. Filesystem PASS does NOT mean the media is healthy.

### Verdict accuracy

The tool's verdict of **UNKNOWN / LOW confidence / Non-critical only**
is **correct and appropriately conservative.** It did not claim the drive
is healthy. It did not claim the drive is failing. It correctly identified
that it cannot make a determination.

### What would change the verdict

- If SMART were available and showed all counters at zero with
  overall PASS → verdict would become **Healthy / HIGH confidence**
- If SMART showed reallocated sectors > 100 → verdict would become
  **Failing / HIGH confidence / Replace now**
- A surface scan (reading raw blocks) could provide partial confidence
  even without SMART, but was not run in this validation

### Final assessment

**The validation results are honest and trustworthy.** The tool correctly
identified its own limitations and did not overstate what it knows. The
drive is in an unknown health state due to USB enclosure limitations,
not due to any observed problem.
