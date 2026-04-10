"""Tests for NVMe evaluation rules.

Uses hand-built SmartSnapshot objects and fixture-driven end-to-end tests.
"""
from __future__ import annotations

import json
from pathlib import Path

from disk_health_checker.checks.smart.nvme import evaluate_nvme
from disk_health_checker.checks.smart.normalize import parse_nvme
from disk_health_checker.models.smart_types import (
    Confidence,
    DriveKind,
    FindingSeverity,
    SmartSnapshot,
    Verdict,
)

FIXTURES = Path(__file__).parent / "fixtures" / "smartctl"


def _snap(**kwargs) -> SmartSnapshot:
    """Build a healthy NVMe snapshot with sensible defaults."""
    defaults = dict(
        device_kind=DriveKind.NVME,
        is_ssd=True,
        overall_passed=True,
        critical_warning_bits=0,
        available_spare_percent=100,
        available_spare_threshold=10,
        percent_life_used=5,
        temperature_c=40,
        media_errors=0,
        power_on_hours=1000,
    )
    defaults.update(kwargs)
    return SmartSnapshot(**defaults)


def _codes(result) -> list[str]:
    return [f.code for f in result.findings]


# ================================================================
#  Healthy drive
# ================================================================

def test_healthy_nvme_passes():
    r = evaluate_nvme(_snap())
    assert r.verdict == Verdict.PASS
    assert r.confidence == Confidence.HIGH
    assert r.score >= 90
    assert len(r.findings) == 0


# ================================================================
#  Overall failed
# ================================================================

def test_overall_failed():
    r = evaluate_nvme(_snap(overall_passed=False))
    assert r.verdict == Verdict.FAIL
    assert "nvme.overall_failed" in _codes(r)


# ================================================================
#  Critical warning bits
# ================================================================

def test_critical_warning_spare_below():
    r = evaluate_nvme(_snap(critical_warning_bits=0x01))
    assert r.verdict == Verdict.FAIL
    assert "nvme.critical_warning.spare_below_threshold" in _codes(r)


def test_critical_warning_temperature():
    r = evaluate_nvme(_snap(critical_warning_bits=0x02))
    assert r.verdict == Verdict.WARNING
    assert "nvme.critical_warning.temperature" in _codes(r)


def test_critical_warning_reliability():
    r = evaluate_nvme(_snap(critical_warning_bits=0x04))
    assert r.verdict == Verdict.FAIL
    assert "nvme.critical_warning.reliability_degraded" in _codes(r)


def test_critical_warning_read_only():
    r = evaluate_nvme(_snap(critical_warning_bits=0x08))
    assert r.verdict == Verdict.FAIL
    assert "nvme.critical_warning.read_only" in _codes(r)


def test_critical_warning_volatile_backup():
    r = evaluate_nvme(_snap(critical_warning_bits=0x10))
    assert r.verdict == Verdict.WARNING
    assert "nvme.critical_warning.volatile_backup" in _codes(r)


def test_critical_warning_persistent_memory():
    r = evaluate_nvme(_snap(critical_warning_bits=0x20))
    assert r.verdict == Verdict.WARNING
    assert "nvme.critical_warning.persistent_memory" in _codes(r)


def test_multiple_critical_warning_bits():
    # bits 0 (spare) + 2 (reliability) = 0x05
    r = evaluate_nvme(_snap(critical_warning_bits=0x05))
    assert r.verdict == Verdict.FAIL
    codes = _codes(r)
    assert "nvme.critical_warning.spare_below_threshold" in codes
    assert "nvme.critical_warning.reliability_degraded" in codes


# ================================================================
#  Available spare
# ================================================================

def test_spare_below_threshold_fail():
    r = evaluate_nvme(_snap(available_spare_percent=5, available_spare_threshold=10))
    assert r.verdict == Verdict.FAIL
    assert "nvme.spare_below_threshold" in _codes(r)


def test_spare_at_threshold_fail():
    r = evaluate_nvme(_snap(available_spare_percent=10, available_spare_threshold=10))
    assert r.verdict == Verdict.FAIL
    assert "nvme.spare_below_threshold" in _codes(r)


def test_spare_low_warn():
    r = evaluate_nvme(_snap(available_spare_percent=15, available_spare_threshold=10))
    assert r.verdict == Verdict.WARNING
    assert "nvme.spare_low" in _codes(r)


def test_spare_21_no_finding():
    r = evaluate_nvme(_snap(available_spare_percent=21))
    assert "nvme.spare_low" not in _codes(r)
    assert "nvme.spare_below_threshold" not in _codes(r)


# ================================================================
#  Wear (percentage_used)
# ================================================================

def test_wear_past_100_warn_not_fail():
    """Per NVMe spec, percentage_used > 100 is normal for worn drives.
    WARNING, not FAIL — the drive may still work."""
    r = evaluate_nvme(_snap(percent_life_used=107))
    assert r.verdict == Verdict.WARNING
    assert "nvme.wear_past_endurance" in _codes(r)
    # Must not be FAIL.
    assert all(f.severity != FindingSeverity.FAIL for f in r.findings
               if f.code.startswith("nvme.wear"))


def test_wear_90_warn():
    r = evaluate_nvme(_snap(percent_life_used=90))
    assert r.verdict == Verdict.WARNING
    assert "nvme.wear_high" in _codes(r)


def test_wear_80_info():
    r = evaluate_nvme(_snap(percent_life_used=80))
    # INFO findings don't trigger WARNING verdict.
    assert r.verdict == Verdict.PASS
    assert "nvme.wear_elevated" in _codes(r)


def test_wear_79_no_finding():
    r = evaluate_nvme(_snap(percent_life_used=79))
    codes = _codes(r)
    assert not any(c.startswith("nvme.wear") for c in codes)


# ================================================================
#  Media errors
# ================================================================

def test_media_errors_warn():
    r = evaluate_nvme(_snap(media_errors=3))
    assert r.verdict == Verdict.WARNING
    assert "nvme.media_errors" in _codes(r)


# ================================================================
#  Temperature
# ================================================================

def test_temperature_above_critical_warn():
    r = evaluate_nvme(_snap(temperature_c=82))
    assert r.verdict == Verdict.WARNING
    assert "nvme.temperature.critical" in _codes(r)


def test_temperature_above_drive_reported_warning():
    r = evaluate_nvme(_snap(temperature_c=72, temperature_warning_c=70))
    assert r.verdict == Verdict.WARNING
    assert "nvme.temperature.warning" in _codes(r)


def test_temperature_normal_no_finding():
    r = evaluate_nvme(_snap(temperature_c=45))
    codes = _codes(r)
    assert not any(c.startswith("nvme.temperature") for c in codes)


# ================================================================
#  Confidence gate
# ================================================================

def test_confidence_high_with_cw_and_spare():
    r = evaluate_nvme(_snap())
    assert r.confidence == Confidence.HIGH


def test_confidence_medium_with_only_cw():
    r = evaluate_nvme(_snap(available_spare_percent=None))
    assert r.confidence == Confidence.MEDIUM


def test_confidence_low_no_nvme_signals():
    r = evaluate_nvme(SmartSnapshot(
        device_kind=DriveKind.NVME,
        is_ssd=True,
    ))
    assert r.confidence == Confidence.LOW
    assert r.verdict == Verdict.UNKNOWN


# ================================================================
#  Fixture-driven end-to-end
# ================================================================

def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_fixture_healthy_passes():
    data = _load("nvme_healthy.synthetic.json")
    snap = parse_nvme(data)
    r = evaluate_nvme(snap)
    assert r.verdict == Verdict.PASS
    assert r.confidence == Confidence.HIGH


def test_fixture_wear_warning():
    data = _load("nvme_wear_warning.synthetic.json")
    snap = parse_nvme(data)
    r = evaluate_nvme(snap)
    assert r.verdict == Verdict.WARNING
    codes = _codes(r)
    assert "nvme.wear_high" in codes
    assert "nvme.spare_low" in codes


def test_fixture_critical_warning_fails():
    data = _load("nvme_critical_warning.synthetic.json")
    snap = parse_nvme(data)
    r = evaluate_nvme(snap)
    assert r.verdict == Verdict.FAIL
    codes = _codes(r)
    # critical_warning=5 → bits 0 (spare below) + 2 (reliability)
    assert "nvme.critical_warning.spare_below_threshold" in codes
    assert "nvme.critical_warning.reliability_degraded" in codes
    # spare=3 < threshold=10
    assert "nvme.spare_below_threshold" in codes
    # percentage_used=107
    assert "nvme.wear_past_endurance" in codes
    # media_errors=47
    assert "nvme.media_errors" in codes
    # temperature=72 with default warning=70
    assert "nvme.temperature.warning" in codes


# ================================================================
#  interpret_smart dispatch
# ================================================================

def test_interpret_smart_dispatches_to_nvme():
    """NVMe data should flow through parse_nvme + evaluate_nvme."""
    from disk_health_checker.checks.smart import interpret_smart

    data = _load("nvme_healthy.synthetic.json")
    result = interpret_smart(data)
    assert result.details["verdict"] == "PASS"
    assert result.details["confidence"] == "HIGH"
    assert result.status.value == "OK"


def test_interpret_smart_nvme_critical():
    from disk_health_checker.checks.smart import interpret_smart

    data = _load("nvme_critical_warning.synthetic.json")
    result = interpret_smart(data)
    assert result.details["verdict"] == "FAIL"
    assert result.status.value == "CRITICAL"
    assert len(result.details["findings"]) > 0
