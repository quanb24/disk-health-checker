"""Parse raw smartctl JSON into a normalized SmartSnapshot.

Pure functions — no I/O, no subprocess calls.

Design rules:
- Every field that cannot be confidently determined is left as None.
- The `parser_notes` list records every inference or fallback so the
  presentation layer can explain where values came from.
- Prefer smartctl's top-level normalized fields (temperature.current,
  power_on_time.hours) over the attribute table. Fall back to the table
  only when top-level fields are absent.
- For attribute-table raw values: use raw.value for monotonic counters
  (reallocated, pending, CRC errors). For temperature and wear, prefer
  the normalized column or raw.string parsing — never arithmetic on a
  packed raw.value without a sanity check.
"""

from __future__ import annotations

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from disk_health_checker.models.smart_types import DriveKind, SmartSnapshot

logger = logging.getLogger(__name__)

# Reasonable bounds for sanity-checking decoded values.
_TEMP_MIN_C = -10
_TEMP_MAX_C = 120
_POH_MAX = 150_000  # ~17 years


def detect_drive_kind(data: Dict[str, Any]) -> DriveKind:
    """Determine drive kind from smartctl JSON."""
    device = data.get("device", {})
    dtype = device.get("type", "").lower()

    if dtype == "nvme" or "nvme_smart_health_information_log" in data:
        return DriveKind.NVME
    if dtype in ("sat", "ata") or "ata_smart_attributes" in data:
        return DriveKind.ATA
    if dtype == "scsi":
        return DriveKind.SCSI
    return DriveKind.UNKNOWN


# ---------------------------------------------------------------
#  Attribute table helpers
# ---------------------------------------------------------------

def _find_attr(
    table: List[Dict[str, Any]],
    names: Tuple[str, ...],
) -> Optional[Dict[str, Any]]:
    """Find the first attribute in `table` whose name matches `names`."""
    for attr in table:
        if attr.get("name") in names:
            return attr
    return None


def _raw_count(attr: Optional[Dict[str, Any]]) -> Optional[int]:
    """Extract raw.value as a plain counter (reallocated, pending, etc.).

    Returns None if the attribute is absent or raw.value is not an int.
    """
    if attr is None:
        return None
    val = attr.get("raw", {}).get("value")
    if isinstance(val, int):
        return val
    return None


def _parse_first_int(s: str) -> Optional[int]:
    """Extract the first integer from a string like '37 (Min/Max 20/45)'."""
    m = re.search(r"-?\d+", s)
    if m:
        return int(m.group())
    return None


def _decode_temperature(
    data: Dict[str, Any],
    table: List[Dict[str, Any]],
    notes: List[str],
) -> Optional[int]:
    """Decode temperature in degrees Celsius.

    Priority:
    1. Top-level temperature.current (already normalized by smartctl).
    2. Attribute table raw.string (parse first integer).
    3. Attribute table raw.value low byte (& 0xFF), with sanity check.
    """
    # 1. Top-level
    top = data.get("temperature", {})
    if isinstance(top, dict):
        current = top.get("current")
        if isinstance(current, (int, float)) and _TEMP_MIN_C <= current <= _TEMP_MAX_C:
            notes.append("temperature sourced from top-level temperature.current")
            return int(current)

    # 2–3. Attribute table
    attr = _find_attr(table, (
        "Temperature_Celsius",
        "Airflow_Temperature_Cel",
        "Temperature_Internal",
    ))
    if attr is None:
        return None

    # 2. raw.string
    raw_str = attr.get("raw", {}).get("string")
    if isinstance(raw_str, str):
        parsed = _parse_first_int(raw_str)
        if parsed is not None and _TEMP_MIN_C <= parsed <= _TEMP_MAX_C:
            notes.append(f"temperature parsed from raw.string '{raw_str}'")
            return parsed

    # 3. raw.value low byte
    raw_val = attr.get("raw", {}).get("value")
    if isinstance(raw_val, int):
        low_byte = raw_val & 0xFF
        if _TEMP_MIN_C <= low_byte <= _TEMP_MAX_C:
            notes.append(
                f"temperature decoded from raw.value low byte "
                f"(raw={raw_val}, decoded={low_byte})"
            )
            return low_byte
        notes.append(
            f"temperature raw.value={raw_val} low_byte={low_byte} "
            f"outside [{_TEMP_MIN_C},{_TEMP_MAX_C}], discarded"
        )
    return None


def _decode_power_on_hours(
    data: Dict[str, Any],
    table: List[Dict[str, Any]],
    notes: List[str],
) -> Optional[int]:
    """Decode power-on hours.

    Priority:
    1. Top-level power_on_time.hours.
    2. Attribute raw.value (usually a plain counter for this attribute).
    """
    # 1. Top-level
    pot = data.get("power_on_time", {})
    if isinstance(pot, dict):
        hours = pot.get("hours")
        if isinstance(hours, int) and hours >= 0:
            notes.append("power_on_hours sourced from top-level power_on_time.hours")
            return hours

    # 2. Attribute table
    attr = _find_attr(table, ("Power_On_Hours", "Power_On_Hours_and_Msec"))
    val = _raw_count(attr)
    if val is not None and val >= 0:
        # Some drives pack milliseconds in the upper word; mask to 32-bit hours.
        if val > _POH_MAX:
            masked = val & 0xFFFFFFFF
            if 0 <= masked <= _POH_MAX:
                notes.append(
                    f"power_on_hours masked from raw.value={val} to {masked}"
                )
                return masked
            notes.append(
                f"power_on_hours raw.value={val} exceeds {_POH_MAX}h, "
                f"masked={masked} also out of range; keeping raw"
            )
        return val
    return None


def _decode_wear(
    table: List[Dict[str, Any]],
    notes: List[str],
) -> Optional[int]:
    """Derive percent_life_used (0=new, 100=end-of-life) from ATA wear attributes.

    Media_Wearout_Indicator (ID 233, Intel): normalized value 100→0.
    Percent_Lifetime_Remain (ID 231, Micron/Crucial): normalized value 100→0.
    Wear_Leveling_Count (ID 177, Samsung): normalized value 100→0; raw.value
    is an erase-cycle counter that increases — do NOT treat raw as health.

    For all three: percent_life_used = 100 - normalized_value.

    Returns None if we cannot confidently determine the value.
    """
    # Try each attribute in preference order.
    candidates = (
        ("Media_Wearout_Indicator",),
        ("Percent_Lifetime_Remain",),
        ("Wear_Leveling_Count",),
    )
    for names in candidates:
        attr = _find_attr(table, names)
        if attr is None:
            continue
        # Use the NORMALIZED value column, not raw.value.
        norm_val = attr.get("value")
        if not isinstance(norm_val, int):
            notes.append(
                f"wear attribute '{names[0]}' found but normalized value "
                f"is not an int: {norm_val!r}"
            )
            continue
        # Normalized values should be 0–200 range (some vendors use >100 for new).
        if not (0 <= norm_val <= 200):
            notes.append(
                f"wear attribute '{names[0]}' normalized value {norm_val} "
                f"outside expected [0,200], skipped"
            )
            continue
        life_used = max(0, 100 - norm_val)
        notes.append(
            f"percent_life_used={life_used} derived from '{names[0]}' "
            f"normalized value={norm_val} (100-norm)"
        )
        return life_used

    return None


# ---------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------

def parse_ata(data: Dict[str, Any]) -> SmartSnapshot:
    """Parse smartctl ATA/SATA JSON into a SmartSnapshot.

    All fields that cannot be confidently read are left as None.
    """
    notes: List[str] = []
    unknown: List[str] = []

    table = data.get("ata_smart_attributes", {}).get("table", [])

    # Identity
    device = data.get("device", {})
    model = data.get("model_name") or device.get("name")
    serial = data.get("serial_number")
    firmware = data.get("firmware_version")
    capacity = data.get("user_capacity", {}).get("bytes")
    rpm = data.get("rotation_rate")

    is_ssd: Optional[bool] = None
    if isinstance(rpm, int):
        is_ssd = rpm == 0
        notes.append(
            f"is_ssd={'True' if is_ssd else 'False'} from rotation_rate={rpm}"
        )

    # Overall health
    smart_status = data.get("smart_status", {})
    overall_passed: Optional[bool] = None
    if "passed" in smart_status:
        overall_passed = bool(smart_status["passed"])
    else:
        unknown.append("smart_status.passed")

    # Key counters
    reallocated = _raw_count(
        _find_attr(table, ("Reallocated_Sector_Ct",))
    )
    pending = _raw_count(
        _find_attr(table, ("Current_Pending_Sector", "Current_Pending_Sector_Count"))
    )
    offline_unc = _raw_count(
        _find_attr(table, ("Offline_Uncorrectable", "Total_Uncorrectable_Errors"))
    )
    reported_unc = _raw_count(
        _find_attr(table, ("Reported_Uncorrect", "Reported_Uncorrectable_Errors"))
    )
    udma_crc = _raw_count(
        _find_attr(table, ("UDMA_CRC_Error_Count",))
    )
    cmd_timeout = _raw_count(
        _find_attr(table, ("Command_Timeout",))
    )

    # Track missing critical counters
    if reallocated is None:
        unknown.append("reallocated_sectors")
    if pending is None:
        unknown.append("pending_sectors")
    if offline_unc is None:
        unknown.append("offline_uncorrectable")

    # Temperature
    temperature = _decode_temperature(data, table, notes)
    if temperature is None:
        unknown.append("temperature_c")

    # Power-on hours
    poh = _decode_power_on_hours(data, table, notes)
    if poh is None:
        unknown.append("power_on_hours")

    # Wear
    wear = _decode_wear(table, notes)
    if wear is None and is_ssd:
        unknown.append("percent_life_used")

    # Self-test capability
    smart_cap = data.get("ata_smart_data", {}).get("capabilities", {})
    supports_self_test: Optional[bool] = None
    if isinstance(smart_cap, dict):
        # smartctl JSON puts self-test support under various keys depending
        # on version. Check the most common structures.
        for key in ("self_tests_supported", "self_test"):
            if key in smart_cap:
                supports_self_test = bool(smart_cap[key])
                break
    # Also check the older top-level key used in the original code.
    if supports_self_test is None:
        legacy_cap = data.get("smart_capabilities", {})
        if isinstance(legacy_cap, dict):
            if legacy_cap.get("self_tests") or legacy_cap.get("self_test"):
                supports_self_test = True

    return SmartSnapshot(
        device_kind=DriveKind.ATA,
        model=model,
        serial=serial,
        firmware=firmware,
        capacity_bytes=capacity,
        rotation_rate_rpm=rpm,
        is_ssd=is_ssd,
        overall_passed=overall_passed,
        power_on_hours=poh,
        temperature_c=temperature,
        reallocated_sectors=reallocated,
        pending_sectors=pending,
        offline_uncorrectable=offline_unc,
        reported_uncorrect=reported_unc,
        udma_crc_errors=udma_crc,
        command_timeouts=cmd_timeout,
        percent_life_used=wear,
        supports_self_test=supports_self_test,
        parser_notes=notes,
        unknown_fields=unknown,
    )


# ---------------------------------------------------------------
#  NVMe parser
# ---------------------------------------------------------------

def _safe_int(val: Any) -> Optional[int]:
    """Return val as int if it is one, else None."""
    return val if isinstance(val, int) else None


def parse_nvme(data: Dict[str, Any]) -> SmartSnapshot:
    """Parse smartctl NVMe JSON into a SmartSnapshot.

    Source fields come from nvme_smart_health_information_log as
    documented in NVMe 1.4 spec section 5.14.1.2 and smartmontools
    JSON output.  All fields are Optional; missing keys produce None.

    NOTE: This parser is built from the NVMe spec + smartmontools docs
    and validated against SYNTHETIC fixtures only.  Field names should
    be verified against a real NVMe capture when available.
    """
    notes: List[str] = []
    unknown: List[str] = []

    log = data.get("nvme_smart_health_information_log", {})
    if not isinstance(log, dict):
        log = {}
        notes.append("nvme_smart_health_information_log missing or not a dict")

    device = data.get("device", {})

    # Identity
    model = data.get("model_name") or device.get("name")
    serial = data.get("serial_number")
    firmware = data.get("firmware_version")
    capacity = data.get("user_capacity", {}).get("bytes")

    # Overall health
    smart_status = data.get("smart_status", {})
    overall_passed: Optional[bool] = None
    if "passed" in smart_status:
        overall_passed = bool(smart_status["passed"])
    else:
        unknown.append("smart_status.passed")

    # Temperature — smartctl typically converts Kelvin to Celsius in
    # the top-level temperature.current field and in the log itself.
    temperature: Optional[int] = None
    top_temp = data.get("temperature", {})
    if isinstance(top_temp, dict) and isinstance(top_temp.get("current"), int):
        temperature = top_temp["current"]
        notes.append("temperature sourced from top-level temperature.current")
    else:
        log_temp = log.get("temperature")
        if isinstance(log_temp, int):
            # smartctl usually reports this in Celsius already.
            if _TEMP_MIN_C <= log_temp <= _TEMP_MAX_C:
                temperature = log_temp
                notes.append("temperature sourced from nvme log temperature field")
            else:
                # Might be Kelvin — try converting.
                converted = log_temp - 273
                if _TEMP_MIN_C <= converted <= _TEMP_MAX_C:
                    temperature = converted
                    notes.append(
                        f"temperature converted from Kelvin: {log_temp}K → {converted}°C"
                    )
                else:
                    notes.append(
                        f"nvme log temperature={log_temp} out of range, discarded"
                    )
    if temperature is None:
        unknown.append("temperature_c")

    # NVMe drive-reported temperature thresholds (from warning_temp_time /
    # critical_comp_time presence; smartctl sometimes exposes these in
    # the temperature object).
    temp_warning_c: Optional[int] = None
    temp_critical_c: Optional[int] = None
    if isinstance(top_temp, dict):
        # Some smartctl versions expose warning/critical thresholds here.
        w = top_temp.get("op_limit")
        c = top_temp.get("crit_limit")
        if isinstance(w, int):
            temp_warning_c = w
        if isinstance(c, int):
            temp_critical_c = c

    # Power-on hours
    poh = _safe_int(log.get("power_on_hours"))
    if poh is None:
        unknown.append("power_on_hours")
    else:
        notes.append("power_on_hours sourced from nvme log")

    # Critical warning bitfield
    critical_warning = _safe_int(log.get("critical_warning"))
    if critical_warning is None:
        unknown.append("critical_warning")

    # Wear / spare
    percentage_used = _safe_int(log.get("percentage_used"))
    if percentage_used is None:
        unknown.append("percentage_used")

    available_spare = _safe_int(log.get("available_spare"))
    available_spare_threshold = _safe_int(log.get("available_spare_threshold"))
    if available_spare is None:
        unknown.append("available_spare")

    # Counters
    media_errors = _safe_int(log.get("media_errors"))
    num_err_log = _safe_int(log.get("num_err_log_entries"))
    unsafe_shutdowns = _safe_int(log.get("unsafe_shutdowns"))
    data_units_written = _safe_int(log.get("data_units_written"))
    data_units_read = _safe_int(log.get("data_units_read"))

    return SmartSnapshot(
        device_kind=DriveKind.NVME,
        model=model,
        serial=serial,
        firmware=firmware,
        capacity_bytes=capacity,
        is_ssd=True,  # NVMe is always flash
        overall_passed=overall_passed,
        power_on_hours=poh,
        temperature_c=temperature,
        temperature_warning_c=temp_warning_c,
        temperature_critical_c=temp_critical_c,
        critical_warning_bits=critical_warning,
        percent_life_used=percentage_used,
        available_spare_percent=available_spare,
        available_spare_threshold=available_spare_threshold,
        media_errors=media_errors,
        num_err_log_entries=num_err_log,
        unsafe_shutdowns=unsafe_shutdowns,
        data_units_written=data_units_written,
        data_units_read=data_units_read,
        parser_notes=notes,
        unknown_fields=unknown,
    )
