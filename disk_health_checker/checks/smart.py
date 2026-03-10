from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ..models.config import SmartConfig
from ..models.results import CheckResult, Severity
from ..utils.platform import which, get_platform_info

logger = logging.getLogger(__name__)


@dataclass
class SmartHealth:
    health_state: str  # HEALTHY / WARNING / FAILING / UNKNOWN
    score: int  # 0–100
    explanation: str
    severity: Severity


def _run_smartctl(device: str) -> Dict[str, Any]:
    """
    Run smartctl and return parsed JSON.

    Uses -H -A -i for a concise, technician-friendly report and -j for JSON.
    On macOS, handles common USB enclosure cases by retrying with -d sat.
    """
    smartctl = which("smartctl")
    if not smartctl:
        raise RuntimeError(
            "smartctl not found on PATH. On macOS, install via Homebrew: 'brew install smartmontools'."
        )

    def invoke(args):
        try:
            return subprocess.run(
                [smartctl, "-H", "-A", "-i", "-j"] + args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
            )
        except OSError as exc:
            raise RuntimeError(f"Failed to execute smartctl: {exc}") from exc

    # First attempt: plain device
    proc = invoke([device])
    info = get_platform_info()

    stderr_lower = (proc.stderr or "").lower()
    # Retry logic for common USB/SATA bridge issues on macOS
    should_retry_sat = (
        info.is_macos
        and proc.returncode != 0
        and any(
            phrase in stderr_lower
            for phrase in [
                "unknown usb bridge",
                "please specify device type with -d",
                "unable to detect device type",
            ]
        )
    )

    if should_retry_sat:
        logger.info("Retrying SMART with '-d sat' for %s due to USB enclosure.", device)
        proc = invoke(["-d", "sat", device])
        stderr_lower = (proc.stderr or "").lower()

    if proc.returncode not in (0, 2):  # smartctl uses 2 for some non-fatal cases
        # Distinguish enclosure/unsupported cases for better messaging
        enclosure_texts = [
            "smart support is: un",
            "device lacks smart capability",
            "smart support is: unavailable",
            "transport error",
        ]
        if any(t in stderr_lower for t in enclosure_texts):
            raise RuntimeError(
                "SMART not available for this device. This is common for some USB enclosures that "
                "do not pass SMART data through. Try connecting the drive directly or using a different enclosure."
            )
        raise RuntimeError(f"smartctl exited with {proc.returncode}: {proc.stderr.strip()}")

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse smartctl JSON output: {exc}") from exc


def _extract_attribute(attributes: list[Dict[str, Any]], names: Tuple[str, ...]) -> Optional[int]:
    for attr in attributes:
        name = attr.get("name")
        if name in names:
            return attr.get("raw", {}).get("value")
    return None


def _score_smart(data: Dict[str, Any]) -> Tuple[SmartHealth, Dict[str, Any]]:
    info = data.get("smart_status", {})
    passed = info.get("passed", False)

    attributes = data.get("ata_smart_attributes", {}).get("table", [])

    # Pull key attributes
    reallocated = _extract_attribute(attributes, ("Reallocated_Sector_Ct",))
    pending = _extract_attribute(attributes, ("Current_Pending_Sector", "Current_Pending_Sector_Count"))
    offline_uncorrectable = _extract_attribute(
        attributes, ("Offline_Uncorrectable", "Total_Uncorrectable_Errors")
    )
    reported_uncorrect = _extract_attribute(
        attributes, ("Reported_Uncorrect", "Reported_Uncorrectable_Errors")
    )
    power_on_hours = _extract_attribute(attributes, ("Power_On_Hours", "Power_On_Hours_and_Msec"))
    temperature = _extract_attribute(
        attributes,
        ("Temperature_Celsius", "Airflow_Temperature_Cel", "Temperature_Internal"),
    )
    wear_indicator = _extract_attribute(
        attributes,
        ("Media_Wearout_Indicator", "Percent_Lifetime_Remain", "Wear_Leveling_Count"),
    )

    # Self-test capability (best-effort)
    smart_cap = data.get("smart_capabilities", {})
    supports_self_test = bool(smart_cap.get("self_tests") or smart_cap.get("self_test"))

    details: Dict[str, Any] = {
        "model_name": data.get("model_name") or data.get("device", {}).get("model_name"),
        "serial_number": data.get("serial_number") or data.get("device", {}).get("serial_number"),
        "firmware_version": data.get("firmware_version"),
        "smart_overall_passed": passed,
        "reallocated_sectors": reallocated,
        "pending_sectors": pending,
        "offline_uncorrectable": offline_uncorrectable,
        "reported_uncorrect": reported_uncorrect,
        "power_on_hours": power_on_hours,
        "temperature_c": temperature,
        "wear_indicator": wear_indicator,
        "supports_self_test": supports_self_test,
    }

    # Compute health state and score
    health_state = "HEALTHY"
    score = 100
    reasons = []

    if not passed:
        health_state = "FAILING"
        score = min(score, 20)
        reasons.append("SMART overall-health self-assessment reports failure.")

    if reallocated is not None:
        if reallocated > 0:
            if reallocated > 100:
                score -= 40
                health_state = "FAILING"
                reasons.append(f"High reallocated sector count ({reallocated}).")
            else:
                score -= 15
                if health_state != "FAILING":
                    health_state = "WARNING"
                reasons.append(f"{reallocated} reallocated sectors present.")

    if pending is not None and pending > 0:
        score -= 50
        health_state = "FAILING"
        reasons.append(f"{pending} pending sectors indicate unstable media.")

    if offline_uncorrectable is not None and offline_uncorrectable > 0:
        score -= 40
        health_state = "FAILING"
        reasons.append(f"{offline_uncorrectable} offline uncorrectable errors recorded.")

    if reported_uncorrect is not None and reported_uncorrect > 0:
        score -= 30
        if health_state != "FAILING":
            health_state = "WARNING"
        reasons.append(f"{reported_uncorrect} reported uncorrectable errors.")

    if temperature is not None:
        if temperature >= 65:
            score -= 30
            if health_state != "FAILING":
                health_state = "WARNING"
            reasons.append(f"Very high drive temperature ({temperature} °C).")
        elif temperature >= 55:
            score -= 15
            if health_state == "HEALTHY":
                health_state = "WARNING"
            reasons.append(f"Elevated drive temperature ({temperature} °C).")

    if wear_indicator is not None:
        # Interpret a few common wear attributes
        # Media_Wearout_Indicator: often 100 (new) down to 0 (worn out)
        # Percent_Lifetime_Remain: often 100 (new) down to 0 (end of life)
        if wear_indicator <= 10:
            score -= 40
            if health_state != "FAILING":
                health_state = "WARNING"
            reasons.append(f"SSD wear indicator is very low ({wear_indicator}).")
        elif wear_indicator <= 30:
            score -= 20
            if health_state == "HEALTHY":
                health_state = "WARNING"
            reasons.append(f"SSD wear indicator is moderate ({wear_indicator}).")

    # Clamp score and provide default explanation
    score = max(0, min(100, score))
    if not reasons:
        reasons.append("No significant SMART warnings detected.")

    explanation = " ".join(reasons)

    # Map to Severity
    if health_state == "HEALTHY":
        severity = Severity.OK
    elif health_state == "WARNING":
        severity = Severity.WARNING
    elif health_state == "FAILING":
        severity = Severity.CRITICAL
    else:
        severity = Severity.UNKNOWN

    health = SmartHealth(
        health_state=health_state,
        score=score,
        explanation=explanation,
        severity=severity,
    )
    return health, details


def interpret_smart(data: Dict[str, Any]) -> CheckResult:
    """
    Parse and score SMART JSON into a CheckResult.
    """
    health, details = _score_smart(data)

    details["health_state"] = health.health_state
    details["health_score"] = health.score
    details["health_explanation"] = health.explanation

    summary = f"{health.health_state} (score {health.score}/100). {health.explanation.split('.')[0]}."

    recommendations = []
    if health.severity == Severity.CRITICAL:
        recommendations.append("Back up data immediately and replace the drive.")
    elif health.severity == Severity.WARNING:
        recommendations.append("Monitor SMART values regularly and ensure backups are up to date.")

    return CheckResult(
        check_name="SMART",
        status=health.severity,
        summary=summary,
        details=details,
        recommendations=recommendations,
    )


def run_smart_check(config: SmartConfig) -> CheckResult:
    """
    Run SMART diagnostics for the given device using smartctl if available.
    """
    try:
        data = _run_smartctl(config.device)
    except Exception as exc:
        logger.warning("SMART check unavailable: %s", exc)
        message = str(exc)
        recommendations = [
            "Ensure the device path is correct.",
            "Run as a privileged user if required by the OS.",
        ]
        if "brew install smartmontools" in message:
            recommendations.insert(0, "On macOS, install smartmontools via Homebrew: 'brew install smartmontools'.")
        if "SMART not available for this device" in message:
            recommendations.insert(
                0,
                "Some USB enclosures do not pass SMART data through. Try a different enclosure or connect via SATA.",
            )

        return CheckResult(
            check_name="SMART",
            status=Severity.UNKNOWN,
            summary=f"SMART check unavailable: {message}",
            details={},
            recommendations=recommendations,
        )

    return interpret_smart(data)




