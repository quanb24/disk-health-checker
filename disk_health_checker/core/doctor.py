from __future__ import annotations

from typing import List

from ..checks.smart import run_smart_check
from ..models.config import SmartConfig
from ..models.results import CheckResult


def _explain_smart(result: CheckResult) -> List[str]:
    """
    Produce beginner-friendly explanations for key SMART warnings.
    """
    d = result.details
    explanations: List[str] = []

    if d.get("reallocated_sectors", 0):
        explanations.append(
            "The drive has had to move data away from some damaged areas (reallocated sectors). "
            "A small number can be acceptable, but if this number grows, the drive is wearing out."
        )
    if d.get("pending_sectors", 0):
        explanations.append(
            "There are sectors the drive is struggling to read reliably (pending sectors). "
            "These can turn into permanent errors and are a strong sign the drive is not trustworthy."
        )
    if d.get("offline_uncorrectable", 0):
        explanations.append(
            "The drive has recorded uncorrectable errors during background checks. "
            "These errors mean the drive could not reliably read some data even with error correction."
        )
    if d.get("reported_uncorrect", 0):
        explanations.append(
            "The drive has reported uncorrectable read errors to the host computer. "
            "This usually shows up as I/O errors in system logs and is a serious reliability warning."
        )
    temp = d.get("temperature_c")
    if isinstance(temp, int):
        if temp >= 55:
            explanations.append(
                f"The drive is running hot ({temp} °C). High temperatures accelerate wear and can cause failures. "
                "Check airflow, enclosure ventilation, and avoid blocking vents."
            )
    wear = d.get("wear_indicator")
    if isinstance(wear, int) and wear <= 30:
        # Only explain wear when the indicator is low enough to be meaningful.
        # For many drives, values near 100 indicate a new or lightly used SSD.
        explanations.append(
            "The SSD wear indicator suggests how much life is left in the flash cells. "
            "A low value means the drive is closer to its designed write endurance limit."
        )

    if not explanations:
        explanations.append(
            "No major SMART warnings were detected. This does not guarantee the drive will never fail, "
            "but it suggests there are no obvious signs of trouble right now."
        )

    return explanations


def run_doctor(device: str) -> CheckResult:
    """
    Run a SMART check and return a CheckResult whose summary and recommendations
    focus on plain-English explanations and next steps.
    """
    smart_result = run_smart_check(SmartConfig(device=device))

    explanations = _explain_smart(smart_result)
    summary = smart_result.summary

    recommendations: List[str] = []
    if smart_result.status.name == "CRITICAL":
        recommendations.append(
            "Treat this drive as unsafe for important data. Back up anything stored on it and plan to replace it."
        )
    elif smart_result.status.name == "WARNING":
        recommendations.append(
            "Use this drive only if you have good backups and are prepared to replace it if the warning indicators grow."
        )
    elif smart_result.status.name == "OK":
        recommendations.append(
            "You can start using this drive, but always keep backups. All drives fail eventually."
        )
    else:
        recommendations.append(
            "The tool could not read SMART data for this device. If it is behind a USB enclosure, "
            "try a different enclosure or connect it directly via SATA if possible."
        )

    return CheckResult(
        check_name="Drive Doctor",
        status=smart_result.status,
        summary=summary,
        # Preserve original SMART details and add human-readable explanations
        details={**smart_result.details, "explanations": explanations},
        # Keep recommendations strictly for actionable guidance
        recommendations=smart_result.recommendations + recommendations,
    )


