from __future__ import annotations

from disk_health_checker.models.smart_types import (
    Confidence,
    DriveKind,
    Finding,
    FindingSeverity,
    SmartSnapshot,
    Verdict,
    VerdictResult,
)


def test_verdict_enum_values():
    assert Verdict.PASS.value == "PASS"
    assert Verdict.WARNING.value == "WARNING"
    assert Verdict.FAIL.value == "FAIL"
    assert Verdict.UNKNOWN.value == "UNKNOWN"
    assert {v for v in Verdict} == {Verdict.PASS, Verdict.WARNING, Verdict.FAIL, Verdict.UNKNOWN}


def test_drivekind_enum_values():
    assert DriveKind.ATA.value == "ata"
    assert DriveKind.NVME.value == "nvme"
    assert DriveKind.UNKNOWN.value == "unknown"


def test_confidence_ordering_is_declared():
    # Not a numeric ordering, but the three levels must exist.
    assert {c for c in Confidence} == {Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW}


def test_smart_snapshot_defaults_are_all_none_or_empty():
    s = SmartSnapshot()
    # Every measurement field defaults to None (missing != zero).
    assert s.overall_passed is None
    assert s.reallocated_sectors is None
    assert s.pending_sectors is None
    assert s.percent_life_used is None
    assert s.available_spare_percent is None
    assert s.critical_warning_bits is None
    assert s.temperature_c is None
    # Provenance defaults.
    assert s.device_kind == DriveKind.UNKNOWN
    assert s.parser_notes == []
    assert s.unknown_fields == []
    assert s.raw_source == "smartctl-json"


def test_smart_snapshot_independent_default_lists():
    # Regression: dataclass mutable defaults must not be shared.
    a = SmartSnapshot()
    b = SmartSnapshot()
    a.parser_notes.append("hello")
    assert b.parser_notes == []


def test_finding_and_verdict_result_construction():
    f = Finding(
        code="ata.reallocated.low",
        severity=FindingSeverity.WARN,
        message="4 reallocated sectors present",
        evidence={"count": 4},
    )
    r = VerdictResult(
        verdict=Verdict.WARNING,
        confidence=Confidence.HIGH,
        score=72,
        findings=[f],
        evidence_missing=[],
        reasoning="1 warning finding, no failures",
    )
    assert r.verdict == Verdict.WARNING
    assert r.findings[0].code == "ata.reallocated.low"
    assert r.findings[0].severity == FindingSeverity.WARN
    assert r.score == 72
    assert r.evidence_missing == []
