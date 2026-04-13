"""SMART health assessment.

Collects SMART data via smartctl, normalizes it into a SmartSnapshot,
evaluates it through ATA or NVMe rules, and converts the VerdictResult
into a CheckResult using the shared evaluation pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from ...models.config import SmartConfig
from ...models.results import CheckResult, Severity
from ...models.smart_types import (
    DriveKind,
    SmartSnapshot,
    VerdictResult,
)
from ..evaluate import verdict_to_check_result
from .collector import collect_smart
from .errors import SmartctlError
from .normalize import detect_drive_kind, parse_ata, parse_nvme
from .ata import evaluate_ata
from .nvme import evaluate_nvme

logger = logging.getLogger(__name__)

# Score weights for SMART findings — kept separate from the default weights
# in evaluate.py because SMART has its own fine-grained deductions defined
# in ata.py and nvme.py (baked into each VerdictResult.score).
# The shared pipeline's compute_score is NOT used for SMART; instead the
# evaluators compute their own scores directly.


def collect_and_interpret(
    device: str, *, transport: str | None = None
) -> Tuple[SmartSnapshot, VerdictResult]:
    """Collect SMART data and return parsed snapshot + verdict.

    This is the shared entry point for both CLI and GUI.  Raises
    SmartctlError subtypes on collection failure — callers handle
    errors according to their own UI conventions.
    """
    result = collect_smart(device, transport=transport)
    kind = detect_drive_kind(result.data)
    if kind == DriveKind.NVME:
        snapshot = parse_nvme(result.data)
        verdict = evaluate_nvme(snapshot)
    else:
        snapshot = parse_ata(result.data)
        verdict = evaluate_ata(snapshot)
    return snapshot, verdict


def interpret_smart(data: Dict[str, Any]) -> CheckResult:
    """Parse and score SMART JSON into a CheckResult.

    Dispatches to ATA or NVMe pipeline based on device kind.
    Uses the shared verdict_to_check_result for consistent output.
    """
    kind = detect_drive_kind(data)

    if kind == DriveKind.NVME:
        snapshot = parse_nvme(data)
        vr = evaluate_nvme(snapshot)
    else:
        snapshot = parse_ata(data)
        vr = evaluate_ata(snapshot)

    # Build SMART-specific extra details (identity, legacy keys).
    extra_details: Dict[str, Any] = {
        # Identity
        "model_name": snapshot.model,
        "serial_number": snapshot.serial,
        "firmware_version": snapshot.firmware,
        "capacity_bytes": snapshot.capacity_bytes,
        "device_kind": snapshot.device_kind.value,
        "is_ssd": snapshot.is_ssd,
        "rotation_rate_rpm": snapshot.rotation_rate_rpm,
        # Legacy attribute keys (used by banner formatter)
        "smart_overall_passed": snapshot.overall_passed,
        "reallocated_sectors": snapshot.reallocated_sectors,
        "pending_sectors": snapshot.pending_sectors,
        "offline_uncorrectable": snapshot.offline_uncorrectable,
        "reported_uncorrect": snapshot.reported_uncorrect,
        "power_on_hours": snapshot.power_on_hours,
        "temperature_c": snapshot.temperature_c,
        "wear_indicator": snapshot.percent_life_used,
        "supports_self_test": snapshot.supports_self_test,
        # NVMe-specific
        "available_spare_percent": snapshot.available_spare_percent,
        "available_spare_threshold": snapshot.available_spare_threshold,
        "critical_warning_bits": snapshot.critical_warning_bits,
        "media_errors": snapshot.media_errors,
        # Legacy compat
        "health_state": _verdict_to_health_state(vr),
        "health_explanation": vr.reasoning,
    }

    return verdict_to_check_result(
        "SMART", vr,
        extra_details=extra_details,
        target_description="SMART diagnostics",
    )


def _verdict_to_health_state(vr: VerdictResult) -> str:
    """Map verdict to legacy HEALTHY/WARNING/FAILING/UNKNOWN labels."""
    from ...models.smart_types import Verdict
    return {
        Verdict.PASS: "HEALTHY",
        Verdict.WARNING: "WARNING",
        Verdict.FAIL: "FAILING",
        Verdict.UNKNOWN: "UNKNOWN",
    }.get(vr.verdict, "UNKNOWN")


def run_smart_check(
    config: SmartConfig, *, transport: str | None = None,
) -> CheckResult:
    """Run SMART diagnostics for the given device using smartctl.

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
            details={
                "failure_reason": "smartctl_not_installed",
                "verdict": "UNKNOWN",
                "confidence": "LOW",
                "health_score": 50,
                "findings": [],
                "evidence_missing": ["smartctl"],
            },
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
                "verdict": "UNKNOWN",
                "confidence": "LOW",
                "health_score": 50,
                "findings": [],
                "evidence_missing": ["smart_data"],
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
            details={
                "failure_reason": "smart_not_supported",
                "verdict": "UNKNOWN",
                "confidence": "LOW",
                "health_score": 50,
                "findings": [],
                "evidence_missing": ["smart_data"],
            },
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
            details={
                "failure_reason": "timeout",
                "verdict": "UNKNOWN",
                "confidence": "LOW",
                "health_score": 50,
                "findings": [],
                "evidence_missing": ["smart_data"],
            },
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
            details={
                "failure_reason": "unknown",
                "verdict": "UNKNOWN",
                "confidence": "LOW",
                "health_score": 50,
                "findings": [],
                "evidence_missing": ["smart_data"],
            },
            recommendations=[
                "Ensure the device path is correct.",
                "Run as a privileged user if required by the OS.",
            ],
        )

    return interpret_smart(result.data)
