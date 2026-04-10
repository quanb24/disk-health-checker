"""Tests for NVMe SMART normalization.

Uses synthetic fixtures and hand-built dicts.
"""
from __future__ import annotations

import json
from pathlib import Path

from disk_health_checker.checks.smart.normalize import parse_nvme, detect_drive_kind
from disk_health_checker.models.smart_types import DriveKind

FIXTURES = Path(__file__).parent / "fixtures" / "smartctl"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


# ---- fixture-driven parsing ----

def test_parse_healthy_nvme_fixture():
    data = _load("nvme_healthy.synthetic.json")
    snap = parse_nvme(data)
    assert snap.device_kind == DriveKind.NVME
    assert snap.is_ssd is True
    assert snap.model == "Samsung SSD 980 PRO 1TB"
    assert snap.serial == "S5GXNF0R000000"
    assert snap.firmware == "5B2QGXA7"
    assert snap.overall_passed is True
    assert snap.temperature_c == 38
    assert snap.critical_warning_bits == 0
    assert snap.available_spare_percent == 100
    assert snap.available_spare_threshold == 10
    assert snap.percent_life_used == 2
    assert snap.media_errors == 0
    assert snap.power_on_hours == 4200
    assert snap.unsafe_shutdowns == 12
    assert snap.data_units_written == 9876543
    assert snap.data_units_read == 12345678


def test_parse_wear_warning_fixture():
    data = _load("nvme_wear_warning.synthetic.json")
    snap = parse_nvme(data)
    assert snap.percent_life_used == 92
    assert snap.available_spare_percent == 15
    assert snap.media_errors == 0
    assert snap.critical_warning_bits == 0


def test_parse_critical_warning_fixture():
    data = _load("nvme_critical_warning.synthetic.json")
    snap = parse_nvme(data)
    assert snap.overall_passed is False
    assert snap.critical_warning_bits == 5  # bits 0 and 2
    assert snap.percent_life_used == 107
    assert snap.available_spare_percent == 3
    assert snap.available_spare_threshold == 10
    assert snap.media_errors == 47
    assert snap.temperature_c == 72


# ---- edge cases ----

def test_missing_log_produces_unknowns():
    data = {
        "device": {"type": "nvme"},
        "smart_status": {"passed": True},
        # No nvme_smart_health_information_log.
    }
    snap = parse_nvme(data)
    assert snap.device_kind == DriveKind.NVME
    assert snap.critical_warning_bits is None
    assert snap.available_spare_percent is None
    assert snap.percent_life_used is None
    assert "critical_warning" in snap.unknown_fields
    assert "available_spare" in snap.unknown_fields
    assert "percentage_used" in snap.unknown_fields


def test_temperature_from_top_level_preferred():
    data = {
        "device": {"type": "nvme"},
        "smart_status": {"passed": True},
        "temperature": {"current": 42},
        "nvme_smart_health_information_log": {"temperature": 45},
    }
    snap = parse_nvme(data)
    assert snap.temperature_c == 42
    assert any("top-level" in n for n in snap.parser_notes)


def test_temperature_from_log_fallback():
    data = {
        "device": {"type": "nvme"},
        "smart_status": {"passed": True},
        "nvme_smart_health_information_log": {"temperature": 50},
    }
    snap = parse_nvme(data)
    assert snap.temperature_c == 50


def test_detect_nvme_by_device_type():
    assert detect_drive_kind({"device": {"type": "nvme"}}) == DriveKind.NVME


def test_detect_nvme_by_log_presence():
    assert detect_drive_kind(
        {"device": {"type": ""}, "nvme_smart_health_information_log": {}}
    ) == DriveKind.NVME
