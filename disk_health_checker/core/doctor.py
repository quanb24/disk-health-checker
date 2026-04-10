from __future__ import annotations

from typing import Dict, List

from ..checks.smart import run_smart_check
from ..models.config import SmartConfig
from ..models.results import CheckResult


# Map finding codes to beginner-friendly explanations.
_EXPLANATIONS: Dict[str, str] = {
    "ata.reallocated.low": (
        "The drive has had to move data away from some damaged areas (reallocated sectors). "
        "A small number can be acceptable, but if this number grows, the drive is wearing out."
    ),
    "ata.reallocated.high": (
        "The drive has a high number of reallocated sectors. This is a strong sign of "
        "significant media degradation. The drive should be replaced."
    ),
    "ata.pending_sectors": (
        "There are sectors the drive is struggling to read reliably (pending sectors). "
        "These can turn into permanent errors and are a strong sign the drive is not trustworthy."
    ),
    "ata.offline_uncorrectable": (
        "The drive has recorded uncorrectable errors during background checks. "
        "These errors mean the drive could not reliably read some data even with error correction."
    ),
    "ata.reported_uncorrect": (
        "The drive has reported uncorrectable read errors to the host computer. "
        "This usually shows up as I/O errors in system logs and is a serious reliability warning."
    ),
    "ata.temperature.elevated": (
        "The drive is running warm. Higher temperatures accelerate wear. "
        "Check airflow, enclosure ventilation, and avoid blocking vents."
    ),
    "ata.temperature.very_high": (
        "The drive is running hot. High temperatures accelerate wear and can cause failures. "
        "Check airflow, enclosure ventilation, and avoid blocking vents."
    ),
    "ata.wear.moderate": (
        "The SSD wear indicator suggests the drive is approaching its designed write endurance limit. "
        "Plan for a replacement in the near future."
    ),
    "ata.wear.critical": (
        "The SSD is near or past its rated endurance limit. "
        "Back up data and replace the drive soon."
    ),
    "ata.udma_crc_errors": (
        "UDMA CRC errors typically indicate a cable or port problem, not a drive failure. "
        "Try replacing the SATA cable or using a different port."
    ),
    "ata.overall_failed": (
        "The drive's own built-in health check reports a failure. "
        "This is the drive itself telling you it is not reliable."
    ),
    "nvme.critical_warning.spare_below_threshold": (
        "The NVMe drive's spare capacity has dropped below its manufacturer-set threshold. "
        "The drive is running out of reserve blocks for wear leveling."
    ),
    "nvme.critical_warning.reliability_degraded": (
        "The NVMe controller reports that the drive's reliability has degraded. "
        "This is a serious warning from the drive's own firmware."
    ),
    "nvme.critical_warning.read_only": (
        "The NVMe drive has placed its media in read-only mode to protect data. "
        "You can still read data, but the drive cannot accept new writes."
    ),
    "nvme.critical_warning.temperature": (
        "The NVMe drive reports a temperature outside its safe operating range."
    ),
    "nvme.critical_warning.volatile_backup": (
        "The NVMe drive's volatile memory backup device has failed. "
        "This may affect data protection during unexpected power loss."
    ),
    "nvme.spare_below_threshold": (
        "The drive's available spare blocks are at or below the manufacturer's threshold. "
        "The drive may not be able to handle further wear gracefully."
    ),
    "nvme.spare_low": (
        "The drive's available spare blocks are getting low. "
        "Monitor this value and plan for replacement."
    ),
    "nvme.wear_past_endurance": (
        "The NVMe drive has been used past its rated endurance. "
        "It may still work, but it is beyond the manufacturer's design life."
    ),
    "nvme.wear_high": (
        "The NVMe drive is approaching its rated endurance limit. "
        "Plan for a replacement."
    ),
    "nvme.media_errors": (
        "The NVMe drive has recorded unrecoverable media errors. "
        "This is uncommon on NVMe and indicates potential media degradation."
    ),
    "nvme.temperature.critical": (
        "The NVMe drive temperature is at or above its critical threshold. "
        "Improve cooling immediately to prevent damage."
    ),
    "nvme.temperature.warning": (
        "The NVMe drive temperature is elevated above its warning threshold. "
        "Check airflow and ventilation."
    ),
    "nvme.overall_failed": (
        "The drive's own built-in health check reports a failure. "
        "This is the drive itself telling you it is not reliable."
    ),
}


def _explain_findings(result: CheckResult) -> List[str]:
    """Produce beginner-friendly explanations from findings in the CheckResult."""
    findings = result.details.get("findings", [])
    explanations: List[str] = []

    for f in findings:
        code = f.get("code", "")
        explanation = _EXPLANATIONS.get(code)
        if explanation:
            explanations.append(explanation)
        else:
            # Fall back to the finding's own message.
            msg = f.get("message", "")
            if msg:
                explanations.append(msg)

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

    explanations = _explain_findings(smart_result)
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
        details={**smart_result.details, "explanations": explanations},
        recommendations=smart_result.recommendations + recommendations,
    )
