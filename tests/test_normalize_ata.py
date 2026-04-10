"""Tests for ATA SMART normalization.

Validates:
- Top-level vs attribute-table temperature sourcing
- Packed raw.value temperature decoding (low-byte extraction)
- Wear indicator: normalized value, not raw counter
- Missing fields → None, not zero
- Parser notes trail for each inference
"""
from __future__ import annotations

from disk_health_checker.checks.smart.normalize import (
    detect_drive_kind,
    parse_ata,
)
from disk_health_checker.models.smart_types import DriveKind


def _base() -> dict:
    """Minimal valid ATA smartctl JSON."""
    return {
        "device": {"type": "sat"},
        "smart_status": {"passed": True},
        "ata_smart_attributes": {"table": []},
    }


# ---- drive kind detection ----

def test_detect_ata():
    assert detect_drive_kind({"device": {"type": "sat"}}) == DriveKind.ATA
    assert detect_drive_kind({"device": {"type": "ata"}}) == DriveKind.ATA
    assert detect_drive_kind({"ata_smart_attributes": {}}) == DriveKind.ATA


def test_detect_nvme():
    assert detect_drive_kind({"device": {"type": "nvme"}}) == DriveKind.NVME
    assert detect_drive_kind({"nvme_smart_health_information_log": {}}) == DriveKind.NVME


def test_detect_scsi():
    assert detect_drive_kind({"device": {"type": "scsi"}}) == DriveKind.SCSI


def test_detect_unknown():
    assert detect_drive_kind({}) == DriveKind.UNKNOWN


# ---- identity ----

def test_identity_fields():
    data = _base()
    data["model_name"] = "Samsung SSD 870 EVO 1TB"
    data["serial_number"] = "S5Y2NX0R123456"
    data["firmware_version"] = "SVT02B6Q"
    data["user_capacity"] = {"bytes": 1000204886016}
    data["rotation_rate"] = 0

    snap = parse_ata(data)
    assert snap.model == "Samsung SSD 870 EVO 1TB"
    assert snap.serial == "S5Y2NX0R123456"
    assert snap.firmware == "SVT02B6Q"
    assert snap.capacity_bytes == 1000204886016
    assert snap.rotation_rate_rpm == 0
    assert snap.is_ssd is True


def test_hdd_detected_by_rotation_rate():
    data = _base()
    data["rotation_rate"] = 7200
    snap = parse_ata(data)
    assert snap.is_ssd is False
    assert snap.rotation_rate_rpm == 7200


# ---- overall health ----

def test_overall_passed_true():
    snap = parse_ata(_base())
    assert snap.overall_passed is True


def test_overall_passed_false():
    data = _base()
    data["smart_status"]["passed"] = False
    snap = parse_ata(data)
    assert snap.overall_passed is False


def test_overall_passed_missing():
    data = _base()
    del data["smart_status"]["passed"]
    snap = parse_ata(data)
    assert snap.overall_passed is None
    assert "smart_status.passed" in snap.unknown_fields


# ---- counters ----

def test_reallocated_sectors():
    data = _base()
    data["ata_smart_attributes"]["table"] = [
        {"name": "Reallocated_Sector_Ct", "raw": {"value": 4}},
    ]
    snap = parse_ata(data)
    assert snap.reallocated_sectors == 4


def test_pending_sectors():
    data = _base()
    data["ata_smart_attributes"]["table"] = [
        {"name": "Current_Pending_Sector", "raw": {"value": 2}},
    ]
    snap = parse_ata(data)
    assert snap.pending_sectors == 2


def test_offline_uncorrectable():
    data = _base()
    data["ata_smart_attributes"]["table"] = [
        {"name": "Offline_Uncorrectable", "raw": {"value": 1}},
    ]
    snap = parse_ata(data)
    assert snap.offline_uncorrectable == 1


def test_missing_counters_are_none_not_zero():
    snap = parse_ata(_base())
    assert snap.reallocated_sectors is None
    assert snap.pending_sectors is None
    assert snap.offline_uncorrectable is None
    assert "reallocated_sectors" in snap.unknown_fields
    assert "pending_sectors" in snap.unknown_fields
    assert "offline_uncorrectable" in snap.unknown_fields


def test_udma_crc_errors():
    data = _base()
    data["ata_smart_attributes"]["table"] = [
        {"name": "UDMA_CRC_Error_Count", "raw": {"value": 3}},
    ]
    snap = parse_ata(data)
    assert snap.udma_crc_errors == 3


# ---- temperature ----

def test_temperature_from_top_level():
    data = _base()
    data["temperature"] = {"current": 37}
    snap = parse_ata(data)
    assert snap.temperature_c == 37
    assert any("top-level" in n for n in snap.parser_notes)


def test_temperature_from_raw_string():
    data = _base()
    data["ata_smart_attributes"]["table"] = [
        {
            "name": "Temperature_Celsius",
            "raw": {"value": 268435493, "string": "37 (Min/Max 20/45)"},
        },
    ]
    snap = parse_ata(data)
    assert snap.temperature_c == 37
    assert any("raw.string" in n for n in snap.parser_notes)


def test_temperature_from_raw_value_low_byte():
    """When raw.string is absent, fall back to raw.value & 0xFF."""
    data = _base()
    data["ata_smart_attributes"]["table"] = [
        {
            "name": "Temperature_Celsius",
            "raw": {"value": 268435493},
            # No raw.string key.
        },
    ]
    snap = parse_ata(data)
    # 268435493 & 0xFF == 37
    assert snap.temperature_c == 37 + (268435493 & 0xFF) - (268435493 & 0xFF)  # just == 37
    assert snap.temperature_c == 268435493 & 0xFF


def test_temperature_insane_value_discarded():
    """A decoded temperature outside [-10, 120] is discarded, not used."""
    data = _base()
    data["ata_smart_attributes"]["table"] = [
        {
            "name": "Temperature_Celsius",
            "raw": {"value": 200},  # low byte = 200, outside range
        },
    ]
    snap = parse_ata(data)
    assert snap.temperature_c is None
    assert "temperature_c" in snap.unknown_fields


def test_temperature_top_level_preferred_over_table():
    """Top-level temperature.current wins even when table has a value."""
    data = _base()
    data["temperature"] = {"current": 42}
    data["ata_smart_attributes"]["table"] = [
        {
            "name": "Temperature_Celsius",
            "raw": {"value": 37, "string": "37"},
        },
    ]
    snap = parse_ata(data)
    assert snap.temperature_c == 42


# ---- power-on hours ----

def test_poh_from_top_level():
    data = _base()
    data["power_on_time"] = {"hours": 8400}
    snap = parse_ata(data)
    assert snap.power_on_hours == 8400
    assert any("top-level" in n for n in snap.parser_notes)


def test_poh_from_attribute():
    data = _base()
    data["ata_smart_attributes"]["table"] = [
        {"name": "Power_On_Hours", "raw": {"value": 12345}},
    ]
    snap = parse_ata(data)
    assert snap.power_on_hours == 12345


# ---- wear indicator (the correctness fix) ----

def test_wear_from_media_wearout_indicator_normalized():
    """Media_Wearout_Indicator: normalized value=95 → 5% life used."""
    data = _base()
    data["rotation_rate"] = 0  # SSD
    data["ata_smart_attributes"]["table"] = [
        {
            "name": "Media_Wearout_Indicator",
            "value": 95,  # normalized column
            "raw": {"value": 0},  # raw is irrelevant for this attribute
        },
    ]
    snap = parse_ata(data)
    assert snap.percent_life_used == 5
    assert any("Media_Wearout_Indicator" in n for n in snap.parser_notes)


def test_wear_from_percent_lifetime_remain():
    """Percent_Lifetime_Remain: normalized value=80 → 20% life used."""
    data = _base()
    data["rotation_rate"] = 0
    data["ata_smart_attributes"]["table"] = [
        {
            "name": "Percent_Lifetime_Remain",
            "value": 80,
            "raw": {"value": 20},
        },
    ]
    snap = parse_ata(data)
    assert snap.percent_life_used == 20


def test_wear_leveling_count_uses_normalized_not_raw():
    """Wear_Leveling_Count: raw.value is an erase counter that increases.
    Only the normalized value (100→0) is a health indicator.
    This is the bug fix from Phase 1 issue #2."""
    data = _base()
    data["rotation_rate"] = 0
    data["ata_smart_attributes"]["table"] = [
        {
            "name": "Wear_Leveling_Count",
            "value": 92,          # normalized: 92% life remaining → 8% used
            "raw": {"value": 1847},  # erase count — NOT a health percent
        },
    ]
    snap = parse_ata(data)
    # Must use normalized (100 - 92 = 8), NOT raw (1847).
    assert snap.percent_life_used == 8
    assert any("Wear_Leveling_Count" in n for n in snap.parser_notes)
    assert any("normalized" in n for n in snap.parser_notes)


def test_wear_missing_on_ssd_is_none_with_unknown():
    """SSD with no wear attribute → None + flagged in unknown_fields."""
    data = _base()
    data["rotation_rate"] = 0
    snap = parse_ata(data)
    assert snap.percent_life_used is None
    assert "percent_life_used" in snap.unknown_fields


def test_wear_missing_on_hdd_is_none_without_unknown():
    """HDD with no wear attribute → None but NOT flagged (HDDs don't have wear)."""
    data = _base()
    data["rotation_rate"] = 7200
    snap = parse_ata(data)
    assert snap.percent_life_used is None
    assert "percent_life_used" not in snap.unknown_fields


# ---- parser notes ----

def test_parser_notes_are_populated():
    """Every inference path should leave at least one note."""
    data = _base()
    data["temperature"] = {"current": 37}
    data["power_on_time"] = {"hours": 100}
    snap = parse_ata(data)
    assert len(snap.parser_notes) >= 2


def test_device_kind_is_ata():
    snap = parse_ata(_base())
    assert snap.device_kind == DriveKind.ATA
