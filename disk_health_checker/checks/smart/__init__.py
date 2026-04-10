from __future__ import annotations

import logging
from typing import Any, Dict

from ...models.config import SmartConfig
from ...models.results import CheckResult, Severity
from ...models.smart_types import DriveKind, FindingSeverity, Verdict
from .collector import collect_smart
from .errors import SmartctlError
from .normalize import detect_drive_kind, parse_ata, parse_nvme
from .ata import evaluate_ata
from .nvme import evaluate_nvme

logger = logging.getLogger(__name__)

# Map Verdict → legacy health_state labels used in details dict.
_VERDICT_TO_HEALTH_STATE = {
    Verdict.PASS: "HEALTHY",
    Verdict.WARNING: "WARNING",
    Verdict.FAIL: "FAILING",
    Verdict.UNKNOWN: "UNKNOWN",
}

# Map Verdict → Severity for CheckResult.status.
_VERDICT_TO_SEVERITY = {
    Verdict.PASS: Severity.OK,
    Verdict.WARNING: Severity.WARNING,
    Verdict.FAIL: Severity.CRITICAL,
    Verdict.UNKNOWN: Severity.UNKNOWN,
}


def interpret_smart(data: Dict[str, Any]) -> CheckResult:
    """Parse and score SMART JSON into a CheckResult.

    Dispatches to ATA or NVMe pipeline based on device kind.
    Preserves the details dict keys that existing callers depend on.
    """
    kind = detect_drive_kind(data)

    if kind == DriveKind.NVME:
        snapshot = parse_nvme(data)
        vr = evaluate_nvme(snapshot)
    else:
        # ATA, SCSI (best-effort via ATA parser), or UNKNOWN.
        snapshot = parse_ata(data)
        vr = evaluate_ata(snapshot)

    health_state = _VERDICT_TO_HEALTH_STATE[vr.verdict]
    severity = _VERDICT_TO_SEVERITY[vr.verdict]

    # Build details dict — includes legacy keys for backwards compat
    # and new structured fields for the banner formatter and JSON output.
    details: Dict[str, Any] = {
        # Identity (used by banner formatter).
        "model_name": snapshot.model,
        "serial_number": snapshot.serial,
        "firmware_version": snapshot.firmware,
        "capacity_bytes": snapshot.capacity_bytes,
        "device_kind": snapshot.device_kind.value,
        "is_ssd": snapshot.is_ssd,
        "rotation_rate_rpm": snapshot.rotation_rate_rpm,
        # Legacy attribute keys.
        "smart_overall_passed": snapshot.overall_passed,
        "reallocated_sectors": snapshot.reallocated_sectors,
        "pending_sectors": snapshot.pending_sectors,
        "offline_uncorrectable": snapshot.offline_uncorrectable,
        "reported_uncorrect": snapshot.reported_uncorrect,
        "power_on_hours": snapshot.power_on_hours,
        "temperature_c": snapshot.temperature_c,
        "wear_indicator": snapshot.percent_life_used,
        "supports_self_test": snapshot.supports_self_test,
        # NVMe-specific (None for ATA, populated for NVMe).
        "available_spare_percent": snapshot.available_spare_percent,
        "available_spare_threshold": snapshot.available_spare_threshold,
        "critical_warning_bits": snapshot.critical_warning_bits,
        "media_errors": snapshot.media_errors,
        # New structured evaluation fields.
        "health_state": health_state,
        "health_score": vr.score,
        "health_explanation": vr.reasoning,
        "verdict": vr.verdict.value,
        "confidence": vr.confidence.value,
        "findings": [
            {
                "code": f.code,
                "severity": f.severity.value,
                "message": f.message,
                "evidence": f.evidence,
            }
            for f in vr.findings
        ],
        "evidence_missing": vr.evidence_missing,
    }

    # Build summary line.
    first_finding = vr.findings[0].message.split(".")[0] if vr.findings else vr.reasoning.split(".")[0]
    summary = f"{health_state} (score {vr.score}/100). {first_finding}."

    recommendations: list[str] = []
    if severity == Severity.CRITICAL:
        recommendations.append("Back up data immediately and replace the drive.")
        recommendations.append("Do not use this drive as sole storage for important data.")
    elif severity == Severity.WARNING:
        recommendations.append("Keep backups current. This drive is usable but has warning signs.")
        recommendations.append("Re-run this check in ~30 days to monitor for progression.")
    elif severity == Severity.OK:
        recommendations.append("No action needed. Keep regular backups as always.")
    else:
        recommendations.append("Could not determine drive health. See signals missing above.")

    return CheckResult(
        check_name="SMART",
        status=severity,
        summary=summary,
        details=details,
        recommendations=recommendations,
    )


def run_smart_check(config: SmartConfig, *, transport: str | None = None) -> CheckResult:
    """
    Run SMART diagnostics for the given device using smartctl if available.

    Args:
        config: SMART check configuration with device path.
        transport: Optional bus protocol hint (e.g. "USB", "SATA", "NVMe")
            from disk enumeration. Enables smarter USB fallback behavior.
    """
    from .errors import (
        SmartctlNotInstalled,
        SmartNotSupported,
        SmartctlTimeout,
        UsbBridgeBlocked,
    )

    try:
        result = collect_smart(config.device, transport=transport)
    except SmartctlNotInstalled as exc:
        logger.warning("smartctl not installed: %s", exc)
        return CheckResult(
            check_name="SMART",
            status=Severity.UNKNOWN,
            summary=f"SMART check unavailable: {exc}",
            details={"failure_reason": "smartctl_not_installed"},
            recommendations=[str(exc), "Ensure the device path is correct."],
        )
    except UsbBridgeBlocked as exc:
        logger.warning("USB bridge blocked SMART: %s", exc.device)
        return CheckResult(
            check_name="SMART",
            status=Severity.UNKNOWN,
            summary=(
                "USB enclosure is blocking SMART data — "
                "the drive itself may be fine, but health cannot be assessed "
                "through this connection."
            ),
            details={
                "failure_reason": "usb_bridge_blocked",
                "device_types_tried": exc.types_tried,
            },
            recommendations=[
                "Connect the drive directly via SATA (not through USB) and re-scan.",
                "Or use a USB dock/adapter known to support SAT passthrough "
                "(e.g. StarTech, Sabrent).",
                "This is a hardware limitation of the enclosure's USB-to-SATA bridge, "
                "not a problem with the drive.",
            ],
        )
    except SmartNotSupported as exc:
        logger.warning("SMART not supported: %s", exc)
        return CheckResult(
            check_name="SMART",
            status=Severity.UNKNOWN,
            summary=f"SMART check unavailable: {exc}",
            details={"failure_reason": "smart_not_supported"},
            recommendations=[
                str(exc),
                "Run as a privileged user if required by the OS.",
            ],
        )
    except SmartctlTimeout as exc:
        logger.warning("smartctl timed out: %s", exc)
        return CheckResult(
            check_name="SMART",
            status=Severity.UNKNOWN,
            summary=f"SMART check unavailable: {exc}",
            details={"failure_reason": "timeout"},
            recommendations=[
                str(exc),
                "The drive may be unresponsive. Try disconnecting and reconnecting.",
            ],
        )
    except SmartctlError as exc:
        logger.warning("SMART check failed: %s", exc)
        return CheckResult(
            check_name="SMART",
            status=Severity.UNKNOWN,
            summary=f"SMART check unavailable: {exc}",
            details={"failure_reason": "unknown"},
            recommendations=[
                "Ensure the device path is correct.",
                "Run as a privileged user if required by the OS.",
            ],
        )

    return interpret_smart(result.data)




