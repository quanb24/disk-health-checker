"""Tests for human and JSON output formatting."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from disk_health_checker.checks.smart import interpret_smart
from disk_health_checker.cli import _print_human_suite, _format_capacity, _format_hours
from disk_health_checker.models.results import SuiteResult


def _make_suite(data: dict) -> SuiteResult:
    check = interpret_smart(data)
    return SuiteResult(
        target="device=/dev/disk2",
        overall_status=check.status,
        check_results=[check],
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )


def _healthy_ata() -> dict:
    return {
        "device": {"type": "sat"},
        "model_name": "Samsung SSD 870 EVO 1TB",
        "serial_number": "S5Y2NX0R123456",
        "firmware_version": "SVT02B6Q",
        "user_capacity": {"bytes": 1000204886016},
        "rotation_rate": 0,
        "smart_status": {"passed": True},
        "temperature": {"current": 37},
        "power_on_time": {"hours": 8400},
        "ata_smart_attributes": {
            "table": [
                {"name": "Reallocated_Sector_Ct", "raw": {"value": 0}},
                {"name": "Current_Pending_Sector", "raw": {"value": 0}},
                {"name": "Offline_Uncorrectable", "raw": {"value": 0}},
            ]
        },
    }


def _warning_ata() -> dict:
    data = _healthy_ata()
    data["ata_smart_attributes"]["table"][0] = {
        "name": "Reallocated_Sector_Ct", "raw": {"value": 6}
    }
    return data


# ---- format helpers ----

def test_format_capacity_tb():
    assert _format_capacity(1000204886016) == "931.5 GB"


def test_format_capacity_none():
    assert _format_capacity(None) == "unknown"


def test_format_hours_short():
    assert _format_hours(12) == "12 hours"


def test_format_hours_days():
    result = _format_hours(720)
    assert "30 days" in result
    assert "720 hours" in result


def test_format_hours_years():
    result = _format_hours(20000)
    assert "years" in result


def test_format_hours_none():
    assert _format_hours(None) == "unknown"


# ---- banner output ----

def test_healthy_banner_shows_pass(capsys):
    suite = _make_suite(_healthy_ata())
    _print_human_suite(suite)
    out = capsys.readouterr().out
    assert "PASS" in out
    assert "Samsung SSD 870 EVO 1TB" in out
    assert "Next steps:" in out
    assert "Signals missing: none" in out


def test_warning_banner_shows_findings(capsys):
    suite = _make_suite(_warning_ata())
    _print_human_suite(suite)
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "reallocated" in out.lower()
    assert "Next steps:" in out


def test_nvme_banner(capsys):
    data = {
        "device": {"type": "nvme"},
        "model_name": "WD Black SN850 2TB",
        "serial_number": "2142H7800000",
        "firmware_version": "613200WD",
        "user_capacity": {"bytes": 2000398934016},
        "smart_status": {"passed": True},
        "temperature": {"current": 45},
        "nvme_smart_health_information_log": {
            "critical_warning": 0,
            "temperature": 45,
            "available_spare": 100,
            "available_spare_threshold": 10,
            "percentage_used": 92,
            "power_on_hours": 28000,
            "media_errors": 0,
            "num_err_log_entries": 0,
            "warning_temp_time": 0,
            "critical_comp_time": 0,
        },
    }
    suite = _make_suite(data)
    _print_human_suite(suite)
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "NVME" in out
    assert "WD Black SN850 2TB" in out
    assert "SSD" in out


def test_unknown_banner_shows_missing(capsys):
    # Empty data -> UNKNOWN
    data = {
        "device": {"type": "sat"},
        "smart_status": {},
        "ata_smart_attributes": {"table": []},
    }
    suite = _make_suite(data)
    _print_human_suite(suite)
    out = capsys.readouterr().out
    assert "UNKNOWN" in out
    assert "Signals missing:" in out


# ---- JSON output ----

def test_json_output_has_structured_fields():
    data = _healthy_ata()
    check = interpret_smart(data)
    suite = SuiteResult(
        target="device=/dev/disk2",
        overall_status=check.status,
        check_results=[check],
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    j = json.loads(json.dumps(suite.to_dict()))

    cr = j["check_results"][0]
    assert cr["details"]["verdict"] == "PASS"
    assert cr["details"]["confidence"] == "HIGH"
    assert isinstance(cr["details"]["findings"], list)
    assert isinstance(cr["details"]["evidence_missing"], list)
    assert cr["details"]["health_score"] == 100
    assert cr["details"]["model_name"] == "Samsung SSD 870 EVO 1TB"
    assert cr["details"]["device_kind"] == "ata"
    assert cr["details"]["capacity_bytes"] == 1000204886016


# ---- schema consistency across all check types ----

REQUIRED_DETAILS_KEYS = {"verdict", "confidence", "health_score", "findings", "evidence_missing"}


def test_schema_smart_check_result():
    """SMART CheckResult.details has all required schema fields."""
    data = _healthy_ata()
    check = interpret_smart(data)
    assert REQUIRED_DETAILS_KEYS.issubset(check.details.keys())


def test_schema_filesystem_check_result():
    """Filesystem CheckResult.details has all required schema fields."""
    import tempfile
    from disk_health_checker.checks.filesystem import run_filesystem_check
    from disk_health_checker.models.config import FsConfig, GlobalConfig

    with tempfile.TemporaryDirectory() as d:
        cfg = FsConfig(mount_point=d)
        gcfg = GlobalConfig()
        result = run_filesystem_check(cfg, gcfg)
        assert REQUIRED_DETAILS_KEYS.issubset(result.details.keys())


def test_schema_surface_scan_check_result():
    """Surface scan CheckResult.details has all required schema fields."""
    from disk_health_checker.checks.surface import run_surface_scan
    from disk_health_checker.models.config import SurfaceScanConfig, GlobalConfig

    cfg = SurfaceScanConfig(device="/dev/nonexistent-test-device")
    gcfg = GlobalConfig()
    result = run_surface_scan(cfg, gcfg)
    assert REQUIRED_DETAILS_KEYS.issubset(result.details.keys())


def test_schema_stress_test_check_result():
    """Stress test CheckResult.details has all required schema fields."""
    from disk_health_checker.checks.stress import run_stress_test
    from disk_health_checker.models.config import StressConfig, GlobalConfig

    cfg = StressConfig(mount_point="/nonexistent-test-path")
    gcfg = GlobalConfig()
    result = run_stress_test(cfg, gcfg)
    assert REQUIRED_DETAILS_KEYS.issubset(result.details.keys())


def test_schema_integrity_check_result():
    """Integrity CheckResult.details has all required schema fields."""
    from disk_health_checker.checks.integrity import run_integrity_check
    from disk_health_checker.models.config import IntegrityConfig, GlobalConfig

    cfg = IntegrityConfig(mount_point="/nonexistent-test-path")
    gcfg = GlobalConfig()
    result = run_integrity_check(cfg, gcfg)
    assert REQUIRED_DETAILS_KEYS.issubset(result.details.keys())


def test_suite_to_dict_json_roundtrip():
    """SuiteResult.to_dict() produces valid JSON with expected structure."""
    data = _healthy_ata()
    suite = _make_suite(data)
    j = json.loads(json.dumps(suite.to_dict()))
    assert "target" in j
    assert "overall_status" in j
    assert "check_results" in j
    assert "started_at" in j
    assert "finished_at" in j
    assert len(j["check_results"]) == 1


def test_json_output_nvme_fields():
    data = {
        "device": {"type": "nvme"},
        "model_name": "Samsung 980 PRO",
        "smart_status": {"passed": True},
        "temperature": {"current": 38},
        "nvme_smart_health_information_log": {
            "critical_warning": 0,
            "available_spare": 100,
            "available_spare_threshold": 10,
            "percentage_used": 5,
            "power_on_hours": 1000,
            "media_errors": 0,
            "num_err_log_entries": 0,
        },
    }
    check = interpret_smart(data)
    d = check.details
    assert d["device_kind"] == "nvme"
    assert d["available_spare_percent"] == 100
    assert d["critical_warning_bits"] == 0
    assert d["is_ssd"] is True
