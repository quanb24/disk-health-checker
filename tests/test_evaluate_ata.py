"""Tests for ATA/SATA evaluation rules.

Tests are grouped by rule, then combinations and confidence gate.
All use hand-built SmartSnapshot objects — no JSON fixtures needed.
"""
from __future__ import annotations

from disk_health_checker.checks.smart.ata import evaluate_ata
from disk_health_checker.models.smart_types import (
    Confidence,
    DriveKind,
    FindingSeverity,
    SmartSnapshot,
    Verdict,
)


def _snap(**kwargs) -> SmartSnapshot:
    """Build a snapshot with sensible defaults for a healthy ATA drive."""
    defaults = dict(
        device_kind=DriveKind.ATA,
        overall_passed=True,
        reallocated_sectors=0,
        pending_sectors=0,
        offline_uncorrectable=0,
        temperature_c=35,
        power_on_hours=5000,
    )
    defaults.update(kwargs)
    return SmartSnapshot(**defaults)


def _codes(result) -> list[str]:
    return [f.code for f in result.findings]


# ================================================================
#  Individual rules
# ================================================================

# ---- overall failed ----

def test_overall_failed():
    r = evaluate_ata(_snap(overall_passed=False))
    assert r.verdict == Verdict.FAIL
    assert "ata.overall_failed" in _codes(r)


# ---- pending sectors ----

def test_pending_sectors_fail():
    r = evaluate_ata(_snap(pending_sectors=1))
    assert r.verdict == Verdict.FAIL
    assert "ata.pending_sectors" in _codes(r)


def test_pending_sectors_zero_ok():
    r = evaluate_ata(_snap(pending_sectors=0))
    assert "ata.pending_sectors" not in _codes(r)


# ---- offline uncorrectable ----

def test_offline_uncorrectable_fail():
    r = evaluate_ata(_snap(offline_uncorrectable=3))
    assert r.verdict == Verdict.FAIL
    assert "ata.offline_uncorrectable" in _codes(r)


# ---- reallocated sectors ----

def test_reallocated_high_fail():
    r = evaluate_ata(_snap(reallocated_sectors=150))
    assert r.verdict == Verdict.FAIL
    assert "ata.reallocated.high" in _codes(r)


def test_reallocated_low_warn():
    r = evaluate_ata(_snap(reallocated_sectors=4))
    assert r.verdict == Verdict.WARNING
    assert "ata.reallocated.low" in _codes(r)


def test_reallocated_zero_ok():
    r = evaluate_ata(_snap(reallocated_sectors=0))
    assert "ata.reallocated.low" not in _codes(r)
    assert "ata.reallocated.high" not in _codes(r)


def test_reallocated_exactly_100_is_warn_not_fail():
    r = evaluate_ata(_snap(reallocated_sectors=100))
    assert r.verdict == Verdict.WARNING
    assert "ata.reallocated.low" in _codes(r)


def test_reallocated_101_is_fail():
    r = evaluate_ata(_snap(reallocated_sectors=101))
    assert r.verdict == Verdict.FAIL
    assert "ata.reallocated.high" in _codes(r)


# ---- reported uncorrect ----

def test_reported_uncorrect_warn():
    r = evaluate_ata(_snap(reported_uncorrect=5))
    assert r.verdict == Verdict.WARNING
    assert "ata.reported_uncorrect" in _codes(r)


# ---- temperature ----

def test_temperature_very_high_warn():
    r = evaluate_ata(_snap(temperature_c=65))
    assert r.verdict == Verdict.WARNING
    assert "ata.temperature.very_high" in _codes(r)


def test_temperature_elevated_warn():
    r = evaluate_ata(_snap(temperature_c=55))
    assert r.verdict == Verdict.WARNING
    assert "ata.temperature.elevated" in _codes(r)


def test_temperature_normal_no_finding():
    r = evaluate_ata(_snap(temperature_c=40))
    codes = _codes(r)
    assert "ata.temperature.very_high" not in codes
    assert "ata.temperature.elevated" not in codes


# ---- wear ----

def test_wear_critical_fail():
    r = evaluate_ata(_snap(percent_life_used=95))
    assert r.verdict == Verdict.FAIL
    assert "ata.wear.critical" in _codes(r)


def test_wear_90_is_fail():
    r = evaluate_ata(_snap(percent_life_used=90))
    assert r.verdict == Verdict.FAIL
    assert "ata.wear.critical" in _codes(r)


def test_wear_moderate_warn():
    r = evaluate_ata(_snap(percent_life_used=75))
    assert r.verdict == Verdict.WARNING
    assert "ata.wear.moderate" in _codes(r)


def test_wear_69_no_finding():
    r = evaluate_ata(_snap(percent_life_used=69))
    codes = _codes(r)
    assert "ata.wear.critical" not in codes
    assert "ata.wear.moderate" not in codes


# ---- UDMA CRC errors ----

def test_udma_crc_warn():
    r = evaluate_ata(_snap(udma_crc_errors=12))
    assert r.verdict == Verdict.WARNING
    assert "ata.udma_crc_errors" in _codes(r)
    # Message must mention cable/connection, not media.
    f = [f for f in r.findings if f.code == "ata.udma_crc_errors"][0]
    assert "cable" in f.message.lower()


# ================================================================
#  Healthy drive
# ================================================================

def test_healthy_drive_passes():
    r = evaluate_ata(_snap())
    assert r.verdict == Verdict.PASS
    assert r.confidence == Confidence.HIGH
    assert r.score >= 90
    assert len(r.findings) == 0
    assert len(r.evidence_missing) == 0


# ================================================================
#  Score
# ================================================================

def test_score_decreases_with_multiple_findings():
    r_clean = evaluate_ata(_snap())
    r_warn = evaluate_ata(_snap(reallocated_sectors=4, temperature_c=58))
    assert r_warn.score < r_clean.score


def test_score_clamped_at_zero():
    r = evaluate_ata(_snap(
        overall_passed=False,
        pending_sectors=10,
        offline_uncorrectable=5,
        reallocated_sectors=200,
    ))
    assert r.score == 0


def test_verdict_determined_by_worst_finding_not_score():
    """A single FAIL finding → FAIL verdict, even if score is high."""
    r = evaluate_ata(_snap(pending_sectors=1))
    # Score drops by 50 → 50, but verdict is FAIL not WARNING.
    assert r.verdict == Verdict.FAIL


# ================================================================
#  Confidence gate
# ================================================================

def test_confidence_high_with_full_signals():
    r = evaluate_ata(_snap())
    assert r.confidence == Confidence.HIGH


def test_confidence_medium_with_only_overall():
    """overall_passed present but all counters missing → MEDIUM confidence, UNKNOWN verdict.

    Even with MEDIUM confidence, missing attribute counters force UNKNOWN
    verdict to prevent false PASS on USB-bridged drives.
    """
    r = evaluate_ata(_snap(
        reallocated_sectors=None,
        pending_sectors=None,
        offline_uncorrectable=None,
    ))
    assert r.confidence == Confidence.MEDIUM
    assert r.verdict == Verdict.UNKNOWN
    assert any(f.code == "smart.data_unavailable" for f in r.findings)


def test_confidence_medium_with_only_counter():
    """One counter present but overall_passed missing → MEDIUM."""
    r = evaluate_ata(_snap(
        overall_passed=None,
        reallocated_sectors=0,
        pending_sectors=None,
        offline_uncorrectable=None,
    ))
    assert r.confidence == Confidence.MEDIUM


def test_confidence_low_no_signals():
    """Neither overall nor any counter → LOW → verdict UNKNOWN."""
    r = evaluate_ata(SmartSnapshot(
        device_kind=DriveKind.ATA,
        # Everything defaults to None.
    ))
    assert r.confidence == Confidence.LOW
    assert r.verdict == Verdict.UNKNOWN


def test_evidence_missing_tracks_absent_signals():
    r = evaluate_ata(SmartSnapshot(
        device_kind=DriveKind.ATA,
        overall_passed=True,
        # All counters missing.
    ))
    assert "reallocated_sectors" in r.evidence_missing
    assert "pending_sectors" in r.evidence_missing
    assert "offline_uncorrectable" in r.evidence_missing
    assert "temperature_c" in r.evidence_missing


# ================================================================
#  Combinations
# ================================================================

def test_fail_beats_warn():
    """When both FAIL and WARN findings exist, verdict is FAIL."""
    r = evaluate_ata(_snap(
        pending_sectors=2,           # FAIL
        reallocated_sectors=4,       # WARN
        temperature_c=58,            # WARN
    ))
    assert r.verdict == Verdict.FAIL


def test_multiple_warnings():
    r = evaluate_ata(_snap(
        reallocated_sectors=10,
        reported_uncorrect=3,
        temperature_c=56,
    ))
    assert r.verdict == Verdict.WARNING
    assert len([f for f in r.findings if f.severity == FindingSeverity.WARN]) == 3


def test_reasoning_populated():
    r = evaluate_ata(_snap(pending_sectors=1, reallocated_sectors=4))
    assert "failure" in r.reasoning.lower()
    assert "warning" in r.reasoning.lower()
