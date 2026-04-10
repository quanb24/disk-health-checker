"""NVMe SMART evaluation rules.

Pure function: SmartSnapshot -> VerdictResult.  No I/O.

Critical warning bit definitions from NVMe 1.4 spec section 5.14.1.2.
Temperature thresholds prefer drive-reported values when available;
fall back to conservative constants.

NOTE: Rules are built from the NVMe spec and validated against
SYNTHETIC fixtures only.  Verify against a real capture when available.
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

# ---- Score deductions ----
_WEIGHTS = {
    "nvme.overall_failed": 80,
    "nvme.critical_warning.spare_below_threshold": 50,
    "nvme.critical_warning.reliability_degraded": 50,
    "nvme.critical_warning.read_only": 50,
    "nvme.critical_warning.temperature": 20,
    "nvme.critical_warning.volatile_backup": 20,
    "nvme.critical_warning.persistent_memory": 20,
    "nvme.spare_below_threshold": 50,
    "nvme.spare_low": 20,
    "nvme.wear_past_endurance": 30,
    "nvme.wear_high": 15,
    "nvme.wear_elevated": 10,
    "nvme.media_errors": 20,
    "nvme.temperature.critical": 30,
    "nvme.temperature.warning": 15,
    "nvme.critical_comp_time": 15,
}

# Fallback temperature thresholds when the drive doesn't report its own.
_DEFAULT_TEMP_WARNING_C = 70
_DEFAULT_TEMP_CRITICAL_C = 80

# NVMe critical_warning bit masks (NVMe 1.4 §5.14.1.2).
_CW_SPARE_BELOW = 1 << 0
_CW_TEMPERATURE = 1 << 1
_CW_RELIABILITY = 1 << 2
_CW_READ_ONLY = 1 << 3
_CW_VOLATILE_BACKUP = 1 << 4
_CW_PERSISTENT_MEM = 1 << 5


def evaluate_nvme(snap: SmartSnapshot) -> VerdictResult:
    """Evaluate an NVMe SmartSnapshot and return a VerdictResult."""
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
            "nvme.overall_failed", FindingSeverity.FAIL,
            "SMART overall-health self-assessment reports FAILED.",
        )
    elif snap.overall_passed is None:
        evidence_missing.append("smart_status.passed")

    # ---- critical warning bitfield ----
    if snap.critical_warning_bits is not None:
        cw = snap.critical_warning_bits
        if cw & _CW_SPARE_BELOW:
            add(
                "nvme.critical_warning.spare_below_threshold",
                FindingSeverity.FAIL,
                "NVMe critical warning: available spare below threshold.",
            )
        if cw & _CW_RELIABILITY:
            add(
                "nvme.critical_warning.reliability_degraded",
                FindingSeverity.FAIL,
                "NVMe critical warning: NVM subsystem reliability degraded.",
            )
        if cw & _CW_READ_ONLY:
            add(
                "nvme.critical_warning.read_only",
                FindingSeverity.FAIL,
                "NVMe critical warning: media placed in read-only mode.",
            )
        if cw & _CW_TEMPERATURE:
            add(
                "nvme.critical_warning.temperature",
                FindingSeverity.WARN,
                "NVMe critical warning: temperature above or below threshold.",
            )
        if cw & _CW_VOLATILE_BACKUP:
            add(
                "nvme.critical_warning.volatile_backup",
                FindingSeverity.WARN,
                "NVMe critical warning: volatile memory backup device failed.",
            )
        if cw & _CW_PERSISTENT_MEM:
            add(
                "nvme.critical_warning.persistent_memory",
                FindingSeverity.WARN,
                "NVMe critical warning: persistent memory region unreliable.",
            )
    else:
        evidence_missing.append("critical_warning")

    # ---- available spare ----
    if snap.available_spare_percent is not None:
        threshold = snap.available_spare_threshold if snap.available_spare_threshold is not None else 10
        if snap.available_spare_percent <= threshold:
            add(
                "nvme.spare_below_threshold", FindingSeverity.FAIL,
                f"Available spare {snap.available_spare_percent}% is at or below "
                f"threshold ({threshold}%).",
                available_spare=snap.available_spare_percent,
                threshold=threshold,
            )
        elif snap.available_spare_percent <= 20:
            add(
                "nvme.spare_low", FindingSeverity.WARN,
                f"Available spare {snap.available_spare_percent}% is getting low.",
                available_spare=snap.available_spare_percent,
            )
    else:
        evidence_missing.append("available_spare")

    # ---- percentage used (wear) ----
    # Per NVMe spec, percentage_used CAN exceed 100. A drive past 100%
    # is past its rated endurance but may still function.
    if snap.percent_life_used is not None:
        if snap.percent_life_used >= 100:
            add(
                "nvme.wear_past_endurance", FindingSeverity.WARN,
                f"NVMe wear: {snap.percent_life_used}% used — past rated endurance. "
                f"Drive may still work but is beyond manufacturer's design life.",
                percent_used=snap.percent_life_used,
            )
        elif snap.percent_life_used >= 90:
            add(
                "nvme.wear_high", FindingSeverity.WARN,
                f"NVMe wear: {snap.percent_life_used}% used — approaching endurance limit.",
                percent_used=snap.percent_life_used,
            )
        elif snap.percent_life_used >= 80:
            add(
                "nvme.wear_elevated", FindingSeverity.INFO,
                f"NVMe wear: {snap.percent_life_used}% used — nearing endurance limit.",
                percent_used=snap.percent_life_used,
            )
    else:
        evidence_missing.append("percentage_used")

    # ---- media errors ----
    if snap.media_errors is not None and snap.media_errors > 0:
        add(
            "nvme.media_errors", FindingSeverity.WARN,
            f"{snap.media_errors} unrecoverable media error(s) — "
            f"uncommon on NVMe, indicates potential media degradation.",
            count=snap.media_errors,
        )

    # ---- temperature ----
    if snap.temperature_c is not None:
        crit_c = snap.temperature_critical_c or _DEFAULT_TEMP_CRITICAL_C
        warn_c = snap.temperature_warning_c or _DEFAULT_TEMP_WARNING_C

        if snap.temperature_c >= crit_c:
            add(
                "nvme.temperature.critical", FindingSeverity.WARN,
                f"Drive temperature {snap.temperature_c} °C — "
                f"at or above critical threshold ({crit_c} °C).",
                temperature_c=snap.temperature_c,
                threshold_c=crit_c,
            )
        elif snap.temperature_c >= warn_c:
            add(
                "nvme.temperature.warning", FindingSeverity.WARN,
                f"Drive temperature {snap.temperature_c} °C — "
                f"at or above warning threshold ({warn_c} °C).",
                temperature_c=snap.temperature_c,
                threshold_c=warn_c,
            )

    # ---- Clamp score ----
    score = max(0, min(100, score))

    # ---- Determine worst severity → verdict ----
    has_fail = any(f.severity == FindingSeverity.FAIL for f in findings)
    has_warn = any(f.severity == FindingSeverity.WARN for f in findings)

    # ---- Confidence gate ----
    # NVMe minimum: critical_warning present AND available_spare present.
    has_cw = snap.critical_warning_bits is not None
    has_spare = snap.available_spare_percent is not None

    if has_cw and has_spare:
        confidence = Confidence.HIGH
    elif has_cw or has_spare:
        confidence = Confidence.MEDIUM
    else:
        confidence = Confidence.LOW

    # ---- Map to verdict ----
    if has_fail:
        verdict = Verdict.FAIL
    elif has_warn:
        verdict = Verdict.WARNING
    elif confidence == Confidence.LOW:
        verdict = Verdict.UNKNOWN
    else:
        verdict = Verdict.PASS

    # ---- Reasoning ----
    if verdict == Verdict.PASS:
        reasoning = "No significant NVMe health warnings detected."
    elif verdict == Verdict.UNKNOWN:
        reasoning = (
            "Insufficient NVMe health data to determine drive health. "
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
