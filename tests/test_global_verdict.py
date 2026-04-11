"""Comprehensive tests for the global verdict engine.

Tests every scenario: all healthy, all failing, mixed, conflicts,
missing data, confidence downgrade, edge cases.
"""

from __future__ import annotations

import pytest

from disk_health_checker.models.results import CheckResult, Severity
from disk_health_checker.verdict.engine import (
    compute_global_verdict,
    _compute_confidence,
    _detect_conflicts,
    _determine_health,
    _compute_composite_score,
    _select_key_findings,
)
from disk_health_checker.verdict.types import (
    GlobalConfidence,
    GlobalVerdict,
    OverallHealth,
    RecommendedUsage,
    Urgency,
)


# ── Helpers ──────────────────────────────────────────────────────────


def _make_check(
    name: str,
    verdict: str = "PASS",
    confidence: str = "HIGH",
    score: int = 100,
    findings: list | None = None,
    evidence_missing: list | None = None,
    status: Severity | None = None,
) -> CheckResult:
    """Build a CheckResult with the unified schema for testing."""
    if findings is None:
        findings = []
    if evidence_missing is None:
        evidence_missing = []
    if status is None:
        status = {
            "PASS": Severity.OK,
            "WARNING": Severity.WARNING,
            "FAIL": Severity.CRITICAL,
            "UNKNOWN": Severity.UNKNOWN,
        }[verdict]

    return CheckResult(
        check_name=name,
        status=status,
        summary=f"Test {name} result",
        details={
            "verdict": verdict,
            "confidence": confidence,
            "health_score": score,
            "findings": findings,
            "evidence_missing": evidence_missing,
        },
        recommendations=[],
    )


def _make_finding(
    code: str, severity: str = "FAIL", check: str = "SMART", message: str = "",
) -> dict:
    return {
        "code": code,
        "severity": severity,
        "message": message or f"{check} finding: {code}",
        "evidence": {},
    }


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: ALL CHECKS HEALTHY
# ══════════════════════════════════════════════════════════════════════


class TestAllHealthy:
    def test_all_pass_returns_healthy(self):
        checks = [
            _make_check("SMART", verdict="PASS", confidence="HIGH", score=100),
            _make_check("Filesystem", verdict="PASS", confidence="HIGH", score=100),
            _make_check("SurfaceScan", verdict="PASS", confidence="HIGH", score=100),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health == OverallHealth.HEALTHY
        assert gv.urgency == Urgency.NO_ACTION
        assert gv.usage == RecommendedUsage.PRIMARY
        assert gv.composite_score == 100
        assert len(gv.key_findings) == 0
        assert len(gv.conflicts) == 0

    def test_healthy_verdict_has_reasoning(self):
        checks = [
            _make_check("SMART"),
            _make_check("Filesystem"),
        ]
        gv = compute_global_verdict(checks)
        assert "Healthy" in gv.reasoning
        assert "passed" in gv.reasoning.lower()

    def test_healthy_confidence_is_high_with_smart_and_others(self):
        checks = [
            _make_check("SMART", confidence="HIGH"),
            _make_check("Filesystem", confidence="HIGH"),
            _make_check("SurfaceScan", confidence="HIGH"),
        ]
        gv = compute_global_verdict(checks)
        assert gv.confidence == GlobalConfidence.HIGH


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: ALL CHECKS FAILING
# ══════════════════════════════════════════════════════════════════════


class TestAllFailing:
    def test_all_fail_returns_failing(self):
        checks = [
            _make_check("SMART", verdict="FAIL", score=10, findings=[
                _make_finding("ata.overall_failed", "FAIL", "SMART"),
            ]),
            _make_check("SurfaceScan", verdict="FAIL", score=20, findings=[
                _make_finding("surface.read_errors", "FAIL", "SurfaceScan"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health == OverallHealth.FAILING
        assert gv.urgency == Urgency.REPLACE_NOW
        assert gv.usage == RecommendedUsage.DO_NOT_TRUST

    def test_smart_fail_alone_is_failing(self):
        checks = [
            _make_check("SMART", verdict="FAIL", score=10, findings=[
                _make_finding("ata.overall_failed", "FAIL", "SMART"),
            ]),
            _make_check("Filesystem", verdict="PASS"),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health == OverallHealth.FAILING
        assert "SMART" in gv.reasoning

    def test_failing_has_key_findings(self):
        checks = [
            _make_check("SMART", verdict="FAIL", findings=[
                _make_finding("ata.pending_sectors", "FAIL", "SMART", "5 pending sectors"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert len(gv.key_findings) >= 1
        assert gv.key_findings[0]["code"] == "ata.pending_sectors"


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: SINGLE FAIL IN NON-SMART CHECK → AT RISK
# ══════════════════════════════════════════════════════════════════════


class TestAtRisk:
    def test_surface_fail_with_smart_pass_is_at_risk(self):
        checks = [
            _make_check("SMART", verdict="PASS"),
            _make_check("SurfaceScan", verdict="FAIL", findings=[
                _make_finding("surface.read_errors", "FAIL", "SurfaceScan"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health == OverallHealth.AT_RISK
        assert gv.urgency == Urgency.BACKUP_NOW

    def test_stress_fail_alone_is_at_risk(self):
        checks = [
            _make_check("SMART", verdict="PASS"),
            _make_check("StressTest", verdict="FAIL", findings=[
                _make_finding("stress.io_errors", "FAIL", "StressTest"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health == OverallHealth.AT_RISK

    def test_multiple_non_smart_fails_escalates_to_failing(self):
        """Failures in 2+ checks = FAILING even without SMART failure."""
        checks = [
            _make_check("SMART", verdict="PASS"),
            _make_check("SurfaceScan", verdict="FAIL", findings=[
                _make_finding("surface.read_errors", "FAIL", "SurfaceScan"),
            ]),
            _make_check("Integrity", verdict="FAIL", findings=[
                _make_finding("integrity.pattern_mismatch", "FAIL", "Integrity"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health == OverallHealth.FAILING


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: WARNINGS → WATCH / DEGRADING
# ══════════════════════════════════════════════════════════════════════


class TestWarnings:
    def test_single_smart_warning_only_is_watch(self):
        """Only SMART has a warning, no other check to conflict → WATCH."""
        checks = [
            _make_check("SMART", verdict="WARNING", findings=[
                _make_finding("ata.temperature.elevated", "WARN", "SMART"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health == OverallHealth.WATCH
        assert gv.urgency == Urgency.MONITOR
        assert gv.usage == RecommendedUsage.SECONDARY

    def test_smart_warn_with_pass_elsewhere_is_degrading(self):
        """SMART WARNING + Filesystem PASS creates a conflict → DEGRADING."""
        checks = [
            _make_check("SMART", verdict="WARNING", findings=[
                _make_finding("ata.temperature.elevated", "WARN", "SMART"),
            ]),
            _make_check("Filesystem", verdict="PASS"),
        ]
        gv = compute_global_verdict(checks)
        # SMART=WARNING vs Filesystem=PASS is a cross-direction conflict
        assert gv.health == OverallHealth.DEGRADING

    def test_smart_warn_plus_surface_warn_is_degrading(self):
        checks = [
            _make_check("SMART", verdict="WARNING", findings=[
                _make_finding("ata.reallocated.low", "WARN", "SMART"),
            ]),
            _make_check("SurfaceScan", verdict="WARNING", findings=[
                _make_finding("surface.slow_blocks", "WARN", "SurfaceScan"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health == OverallHealth.DEGRADING
        assert gv.urgency == Urgency.RECHECK_SOON
        assert gv.usage == RecommendedUsage.NON_CRITICAL

    def test_non_smart_warning_with_smart_pass_creates_conflict(self):
        """SMART PASS + Surface WARNING → conflict → DEGRADING."""
        checks = [
            _make_check("SMART", verdict="PASS"),
            _make_check("SurfaceScan", verdict="WARNING", findings=[
                _make_finding("surface.slow_blocks", "WARN", "SurfaceScan"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        # Cross-direction (PASS vs WARNING) → conflict + warn → DEGRADING
        assert gv.health == OverallHealth.DEGRADING

    def test_non_smart_warning_alone_is_watch(self):
        """Single check with warning, no SMART → WATCH (no conflict possible)."""
        checks = [
            _make_check("SurfaceScan", verdict="WARNING", findings=[
                _make_finding("surface.slow_blocks", "WARN", "SurfaceScan"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health == OverallHealth.WATCH


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: CONFLICTS BETWEEN CHECKS
# ══════════════════════════════════════════════════════════════════════


class TestConflicts:
    def test_smart_pass_surface_fail_creates_conflict(self):
        checks = [
            _make_check("SMART", verdict="PASS"),
            _make_check("SurfaceScan", verdict="FAIL", findings=[
                _make_finding("surface.read_errors", "FAIL", "SurfaceScan"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert len(gv.conflicts) >= 1
        conflict = gv.conflicts[0]
        assert "SMART" in conflict.check_a or "SMART" in conflict.check_b
        assert "SurfaceScan" in conflict.check_a or "SurfaceScan" in conflict.check_b
        assert "conflict" in gv.reasoning.lower() or "inconsistency" in gv.reasoning.lower() or "Conflict" in gv.reasoning

    def test_smart_pass_stress_warn_creates_conflict(self):
        checks = [
            _make_check("SMART", verdict="PASS"),
            _make_check("StressTest", verdict="WARNING", findings=[
                _make_finding("stress.no_ops_completed", "WARN", "StressTest"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert len(gv.conflicts) >= 1

    def test_both_pass_no_conflict(self):
        checks = [
            _make_check("SMART", verdict="PASS"),
            _make_check("SurfaceScan", verdict="PASS"),
        ]
        gv = compute_global_verdict(checks)
        assert len(gv.conflicts) == 0

    def test_both_fail_no_conflict(self):
        """Same-direction results are not conflicts — they reinforce."""
        checks = [
            _make_check("SMART", verdict="FAIL", findings=[
                _make_finding("ata.overall_failed", "FAIL"),
            ]),
            _make_check("SurfaceScan", verdict="FAIL", findings=[
                _make_finding("surface.read_errors", "FAIL"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert len(gv.conflicts) == 0

    def test_conflict_with_warn_worsens_degrading(self):
        """Conflict + warnings → DEGRADING, not just WATCH."""
        checks = [
            _make_check("SMART", verdict="PASS"),
            _make_check("SurfaceScan", verdict="WARNING", findings=[
                _make_finding("surface.slow_blocks", "WARN", "SurfaceScan"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        # Conflict exists + warning → should be DEGRADING
        assert gv.health == OverallHealth.DEGRADING


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: MISSING DATA / INCOMPLETE CHECKS
# ══════════════════════════════════════════════════════════════════════


class TestMissingData:
    def test_no_checks_returns_unknown(self):
        gv = compute_global_verdict([])
        assert gv.health == OverallHealth.UNKNOWN
        assert gv.confidence == GlobalConfidence.LOW

    def test_smart_unknown_returns_unknown(self):
        checks = [
            _make_check("SMART", verdict="UNKNOWN", confidence="LOW"),
            _make_check("Filesystem", verdict="PASS"),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health == OverallHealth.UNKNOWN
        assert "SMART" in gv.reasoning

    def test_no_smart_at_all_caps_confidence(self):
        """Without SMART, global confidence can't be HIGH."""
        checks = [
            _make_check("Filesystem", verdict="PASS", confidence="HIGH"),
            _make_check("SurfaceScan", verdict="PASS", confidence="HIGH"),
        ]
        gv = compute_global_verdict(checks)
        assert gv.confidence != GlobalConfidence.HIGH

    def test_single_check_caps_confidence_at_medium(self):
        checks = [
            _make_check("SMART", verdict="PASS", confidence="HIGH"),
        ]
        gv = compute_global_verdict(checks)
        assert gv.confidence == GlobalConfidence.MEDIUM

    def test_all_low_confidence_returns_low(self):
        checks = [
            _make_check("SMART", verdict="PASS", confidence="LOW"),
            _make_check("Filesystem", verdict="PASS", confidence="LOW"),
        ]
        gv = compute_global_verdict(checks)
        assert gv.confidence == GlobalConfidence.LOW

    def test_low_confidence_prevents_healthy(self):
        """NEVER return Healthy when confidence is LOW."""
        checks = [
            _make_check("SMART", verdict="PASS", confidence="LOW"),
            _make_check("Filesystem", verdict="PASS", confidence="LOW"),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health != OverallHealth.HEALTHY


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: CONFIDENCE COMPUTATION
# ══════════════════════════════════════════════════════════════════════


class TestConfidence:
    def test_smart_high_plus_others_high(self):
        c = _compute_confidence(
            {"SMART": "HIGH", "Filesystem": "HIGH", "SurfaceScan": "HIGH"},
            smart_ran=True, total_checks=3,
        )
        assert c == GlobalConfidence.HIGH

    def test_smart_high_one_other_medium(self):
        c = _compute_confidence(
            {"SMART": "HIGH", "Filesystem": "MEDIUM"},
            smart_ran=True, total_checks=2,
        )
        assert c == GlobalConfidence.MEDIUM

    def test_smart_low_always_low(self):
        c = _compute_confidence(
            {"SMART": "LOW", "Filesystem": "HIGH"},
            smart_ran=True, total_checks=2,
        )
        assert c == GlobalConfidence.LOW

    def test_no_smart_ran(self):
        c = _compute_confidence(
            {"Filesystem": "HIGH", "SurfaceScan": "HIGH"},
            smart_ran=False, total_checks=2,
        )
        assert c in (GlobalConfidence.LOW, GlobalConfidence.MEDIUM)

    def test_empty_is_low(self):
        c = _compute_confidence({}, smart_ran=False, total_checks=0)
        assert c == GlobalConfidence.LOW


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: COMPOSITE SCORE
# ══════════════════════════════════════════════════════════════════════


class TestCompositeScore:
    def test_all_100(self):
        checks = [
            _make_check("SMART", score=100),
            _make_check("Filesystem", score=100),
        ]
        assert _compute_composite_score(checks) == 100

    def test_smart_weighted_3x(self):
        """SMART score of 50 + Filesystem 100 → weighted avg = (50*3 + 100*1) / 4 = 62.5 → 62"""
        checks = [
            _make_check("SMART", score=50),
            _make_check("Filesystem", score=100),
        ]
        assert _compute_composite_score(checks) == 62

    def test_no_checks_is_zero(self):
        assert _compute_composite_score([]) == 0


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: KEY FINDINGS SELECTION
# ══════════════════════════════════════════════════════════════════════


class TestKeyFindings:
    def test_all_fails_included(self):
        fails = [
            {"code": "a", "severity": "FAIL", "message": "m1"},
            {"code": "b", "severity": "FAIL", "message": "m2"},
        ]
        warns = [
            {"code": "c", "severity": "WARN", "message": "m3"},
        ]
        key = _select_key_findings(fails, warns)
        assert len(key) == 3

    def test_warns_capped_when_many_fails(self):
        fails = [{"code": f"f{i}", "severity": "FAIL", "message": f"m{i}"} for i in range(6)]
        warns = [{"code": "w1", "severity": "WARN", "message": "w"}]
        key = _select_key_findings(fails, warns)
        # All 6 fails + 0 warns (5 cap exceeded by fails alone)
        assert len(key) == 6

    def test_empty(self):
        assert _select_key_findings([], []) == []


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: DETERMINISM
# ══════════════════════════════════════════════════════════════════════


class TestDeterminism:
    def test_same_input_same_output(self):
        checks = [
            _make_check("SMART", verdict="WARNING", findings=[
                _make_finding("ata.reallocated.low", "WARN"),
            ]),
            _make_check("SurfaceScan", verdict="PASS"),
        ]
        gv1 = compute_global_verdict(checks)
        gv2 = compute_global_verdict(checks)
        assert gv1.health == gv2.health
        assert gv1.urgency == gv2.urgency
        assert gv1.usage == gv2.usage
        assert gv1.confidence == gv2.confidence
        assert gv1.composite_score == gv2.composite_score
        assert gv1.reasoning == gv2.reasoning


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: SERIALIZATION
# ══════════════════════════════════════════════════════════════════════


class TestSerialization:
    def test_to_dict_has_all_fields(self):
        checks = [
            _make_check("SMART", verdict="PASS"),
            _make_check("Filesystem", verdict="PASS"),
        ]
        gv = compute_global_verdict(checks)
        d = gv.to_dict()
        assert "health" in d
        assert "urgency" in d
        assert "recommended_usage" in d
        assert "confidence" in d
        assert "composite_score" in d
        assert "reasoning" in d
        assert "check_verdicts" in d
        assert "key_findings" in d
        assert "conflicts" in d
        assert "all_findings_count" in d

    def test_suite_result_includes_global_verdict(self):
        from datetime import datetime, timezone
        from disk_health_checker.models.results import SuiteResult

        checks = [_make_check("SMART"), _make_check("Filesystem")]
        gv = compute_global_verdict(checks)
        suite = SuiteResult(
            target="test",
            overall_status=Severity.OK,
            check_results=checks,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            global_verdict=gv,
        )
        d = suite.to_dict()
        assert "global_verdict" in d
        assert d["global_verdict"]["health"] == "Healthy"

    def test_suite_result_without_global_verdict(self):
        from datetime import datetime, timezone
        from disk_health_checker.models.results import SuiteResult

        checks = [_make_check("SMART")]
        suite = SuiteResult(
            target="test",
            overall_status=Severity.OK,
            check_results=checks,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )
        d = suite.to_dict()
        assert "global_verdict" not in d


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: HEALTH SAFETY INVARIANTS
# ══════════════════════════════════════════════════════════════════════


class TestSafetyInvariants:
    """These are the hard rules that must NEVER be violated."""

    def test_never_healthy_with_fail_finding(self):
        """NEVER return Healthy if any FAIL finding exists."""
        checks = [
            _make_check("SMART", verdict="PASS"),
            _make_check("Filesystem", verdict="FAIL", findings=[
                _make_finding("fs.mount_not_found", "FAIL"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health != OverallHealth.HEALTHY

    def test_never_healthy_with_low_confidence(self):
        """NEVER return Healthy if confidence is LOW."""
        checks = [
            _make_check("SMART", verdict="PASS", confidence="LOW"),
            _make_check("Filesystem", verdict="PASS", confidence="LOW"),
        ]
        gv = compute_global_verdict(checks)
        assert gv.health != OverallHealth.HEALTHY

    def test_smart_fail_always_failing(self):
        """SMART failure is always the worst outcome — FAILING."""
        for other_verdict in ["PASS", "WARNING", "FAIL", "UNKNOWN"]:
            checks = [
                _make_check("SMART", verdict="FAIL", findings=[
                    _make_finding("ata.overall_failed", "FAIL"),
                ]),
                _make_check("Filesystem", verdict=other_verdict),
            ]
            gv = compute_global_verdict(checks)
            assert gv.health == OverallHealth.FAILING, (
                f"SMART FAIL + Filesystem {other_verdict} should be FAILING, "
                f"got {gv.health}"
            )

    def test_urgency_never_no_action_when_failing(self):
        checks = [
            _make_check("SMART", verdict="FAIL", findings=[
                _make_finding("ata.overall_failed", "FAIL"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert gv.urgency != Urgency.NO_ACTION

    def test_usage_never_primary_when_failing(self):
        checks = [
            _make_check("SMART", verdict="FAIL", findings=[
                _make_finding("ata.overall_failed", "FAIL"),
            ]),
        ]
        gv = compute_global_verdict(checks)
        assert gv.usage != RecommendedUsage.PRIMARY


# ══════════════════════════════════════════════════════════════════════
#  SCENARIO: CONFLICT DETECTION EDGE CASES
# ══════════════════════════════════════════════════════════════════════


class TestConflictDetectionEdgeCases:
    def test_unknown_vs_pass_no_conflict(self):
        """UNKNOWN checks shouldn't create conflicts with passing checks."""
        verdicts = {"SMART": "PASS", "SurfaceScan": "UNKNOWN"}
        # UNKNOWN is not PASS and not FAIL/WARNING, so no cross-direction
        conflicts = _detect_conflicts(verdicts)
        assert len(conflicts) == 0

    def test_three_checks_multiple_conflicts(self):
        verdicts = {
            "SMART": "PASS",
            "SurfaceScan": "FAIL",
            "StressTest": "WARNING",
        }
        conflicts = _detect_conflicts(verdicts)
        # SMART/PASS vs SurfaceScan/FAIL → conflict
        # SMART/PASS vs StressTest/WARNING → conflict
        # SurfaceScan/FAIL vs StressTest/WARNING → same direction, no conflict
        assert len(conflicts) == 2
