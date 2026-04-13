"""ATA/SATA SMART evaluation rules.

Pure function: SmartSnapshot -> VerdictResult.  No I/O.

The verdict is determined by the worst finding, NOT by the score.
The score is advisory — it provides a rough sense of how far the drive
is from ideal, but a single FAIL finding makes the verdict FAIL
regardless of score.

Confidence gate: the verdict is only PASS (or WARNING) when a minimum
evidence floor is met.  If critical signals are missing, the verdict
degrades to UNKNOWN even if everything we *did* read looks fine.
"""

from __future__ import annotations

from disk_health_checker.models.smart_types import (
    Confidence,
    Finding,
    FindingSeverity,
    SmartSnapshot,
    Verdict,
    VerdictResult,
)


# ---- Score deductions per finding ----
_WEIGHTS = {
    "ata.overall_failed": 80,
    "ata.pending_sectors": 50,
    "ata.offline_uncorrectable": 40,
    "ata.reallocated.high": 40,
    "ata.reallocated.low": 15,
    "ata.reported_uncorrect": 30,
    "ata.wear.critical": 40,
    "ata.wear.moderate": 20,
    "ata.temperature.very_high": 30,
    "ata.temperature.elevated": 15,
    "ata.udma_crc_errors": 10,
    "smart.data_unavailable": 0,
}


def evaluate_ata(snap: SmartSnapshot) -> VerdictResult:
    """Evaluate an ATA/SATA SmartSnapshot and return a VerdictResult."""
    findings: list[Finding] = []
    evidence_missing: list[str] = []
    score = 100

    def add(code: str, severity: FindingSeverity, message: str, **evidence):
        nonlocal score
        findings.append(Finding(
            code=code, severity=severity, message=message, evidence=evidence,
        ))
        score -= _WEIGHTS.get(code, 0)

    # ---- overall self-assessment ----
    if snap.overall_passed is False:
        add(
            "ata.overall_failed", FindingSeverity.FAIL,
            "SMART overall-health self-assessment reports FAILED.",
        )
    elif snap.overall_passed is None:
        evidence_missing.append("smart_status.passed")

    # ---- pending sectors ----
    if snap.pending_sectors is not None:
        if snap.pending_sectors > 0:
            add(
                "ata.pending_sectors", FindingSeverity.FAIL,
                f"{snap.pending_sectors} pending sector(s) — unstable media, "
                f"high risk of data loss.",
                count=snap.pending_sectors,
            )
    else:
        evidence_missing.append("pending_sectors")

    # ---- offline uncorrectable ----
    if snap.offline_uncorrectable is not None:
        if snap.offline_uncorrectable > 0:
            add(
                "ata.offline_uncorrectable", FindingSeverity.FAIL,
                f"{snap.offline_uncorrectable} offline uncorrectable error(s) — "
                f"data could not be read even with error correction.",
                count=snap.offline_uncorrectable,
            )
    else:
        evidence_missing.append("offline_uncorrectable")

    # ---- reallocated sectors ----
    if snap.reallocated_sectors is not None:
        if snap.reallocated_sectors > 100:
            add(
                "ata.reallocated.high", FindingSeverity.FAIL,
                f"High reallocated sector count ({snap.reallocated_sectors}).",
                count=snap.reallocated_sectors,
            )
        elif snap.reallocated_sectors > 0:
            add(
                "ata.reallocated.low", FindingSeverity.WARN,
                f"{snap.reallocated_sectors} reallocated sector(s) — "
                f"small reallocation, monitor trend.",
                count=snap.reallocated_sectors,
            )
    else:
        evidence_missing.append("reallocated_sectors")

    # ---- reported uncorrectable ----
    if snap.reported_uncorrect is not None and snap.reported_uncorrect > 0:
        add(
            "ata.reported_uncorrect", FindingSeverity.WARN,
            f"{snap.reported_uncorrect} reported uncorrectable error(s) — "
            f"host-visible read errors.",
            count=snap.reported_uncorrect,
        )

    # ---- temperature ----
    if snap.temperature_c is not None:
        if snap.temperature_c >= 65:
            add(
                "ata.temperature.very_high", FindingSeverity.WARN,
                f"Drive temperature {snap.temperature_c} °C — "
                f"very high, check airflow and ventilation.",
                temperature_c=snap.temperature_c,
            )
        elif snap.temperature_c >= 55:
            add(
                "ata.temperature.elevated", FindingSeverity.WARN,
                f"Drive temperature {snap.temperature_c} °C — "
                f"elevated, consider improving airflow.",
                temperature_c=snap.temperature_c,
            )
    else:
        evidence_missing.append("temperature_c")

    # ---- SSD wear ----
    if snap.percent_life_used is not None:
        if snap.percent_life_used >= 90:
            add(
                "ata.wear.critical", FindingSeverity.FAIL,
                f"SSD wear: {snap.percent_life_used}% life used — "
                f"near or past rated endurance.",
                percent_life_used=snap.percent_life_used,
            )
        elif snap.percent_life_used >= 70:
            add(
                "ata.wear.moderate", FindingSeverity.WARN,
                f"SSD wear: {snap.percent_life_used}% life used — "
                f"approaching endurance limit.",
                percent_life_used=snap.percent_life_used,
            )

    # ---- UDMA CRC errors (cable/connection, not media) ----
    if snap.udma_crc_errors is not None and snap.udma_crc_errors > 0:
        add(
            "ata.udma_crc_errors", FindingSeverity.WARN,
            f"{snap.udma_crc_errors} UDMA CRC error(s) — "
            f"likely a cable or port problem, not media failure.",
            count=snap.udma_crc_errors,
        )

    # ---- Clamp score ----
    score = max(0, min(100, score))

    # ---- Determine worst severity → verdict ----
    has_fail = any(f.severity == FindingSeverity.FAIL for f in findings)
    has_warn = any(f.severity == FindingSeverity.WARN for f in findings)

    # ---- Confidence gate ----
    # Minimum evidence floor for ATA: overall_passed present AND at least
    # one of {reallocated, pending, offline_uncorrectable} readable.
    has_overall = snap.overall_passed is not None
    has_any_counter = any(v is not None for v in [
        snap.reallocated_sectors,
        snap.pending_sectors,
        snap.offline_uncorrectable,
    ])

    if has_overall and has_any_counter:
        confidence = Confidence.HIGH
    elif has_overall or has_any_counter:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    # ---- Insufficient data guard ----
    # If no SMART attribute counters are readable, we cannot assess drive
    # health regardless of overall_passed.  This prevents false PASS
    # results when USB enclosures (or similar) strip attribute data.
    if not has_any_counter:
        add(
            "smart.data_unavailable", FindingSeverity.INFO,
            "SMART attribute data is unavailable — health cannot be "
            "determined from overall status alone.",
        )

    # ---- Map to verdict ----
    if has_fail:
        verdict = Verdict.FAIL
    elif has_warn:
        verdict = Verdict.WARNING
    elif not has_any_counter:
        # Never claim PASS without attribute data, even if overall_passed
        # is present.  USB bridges commonly return overall_passed=True
        # while stripping all counters.
        verdict = Verdict.UNKNOWN
    elif confidence == Confidence.LOW:
        # Cannot claim PASS without minimum evidence.
        verdict = Verdict.UNKNOWN
    else:
        verdict = Verdict.PASS

    # ---- Reasoning summary ----
    if verdict == Verdict.PASS:
        reasoning = "No significant SMART warnings detected."
    elif verdict == Verdict.UNKNOWN:
        reasoning = (
            "Insufficient SMART data to determine drive health. "
            f"Missing: {', '.join(evidence_missing) or 'unknown'}."
        )
    else:
        fail_codes = [f.code for f in findings if f.severity == FindingSeverity.FAIL]
        warn_codes = [f.code for f in findings if f.severity == FindingSeverity.WARN]
        parts = []
        if fail_codes:
            parts.append(f"{len(fail_codes)} failure(s)")
        if warn_codes:
            parts.append(f"{len(warn_codes)} warning(s)")
        reasoning = f"{', '.join(parts)} detected."

    return VerdictResult(
        verdict=verdict,
        confidence=confidence,
        score=score,
        findings=findings,
        evidence_missing=evidence_missing,
        reasoning=reasoning,
    )
