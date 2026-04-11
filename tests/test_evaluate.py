"""Tests for the shared evaluation utilities (checks/evaluate.py)."""

from __future__ import annotations

import pytest

from disk_health_checker.checks.evaluate import (
    compute_score,
    findings_to_verdict,
    verdict_to_check_result,
    _build_recommendations,
)
from disk_health_checker.models.results import Severity
from disk_health_checker.models.smart_types import (
    Confidence,
    Finding,
    FindingSeverity,
    Verdict,
    VerdictResult,
)


# ── compute_score ────────────────────────────────────────────────────


class TestComputeScore:
    def test_no_findings_is_100(self):
        assert compute_score([]) == 100

    def test_known_code_deducts(self):
        f = Finding(code="fs.mount_not_found", severity=FindingSeverity.FAIL, message="x")
        assert compute_score([f]) == 100 - 80

    def test_unknown_code_deducts_zero(self):
        f = Finding(code="unknown.code", severity=FindingSeverity.WARN, message="x")
        assert compute_score([f]) == 100

    def test_custom_weights(self):
        f = Finding(code="custom.code", severity=FindingSeverity.WARN, message="x")
        assert compute_score([f], weights={"custom.code": 25}) == 75

    def test_score_clamped_at_zero(self):
        findings = [
            Finding(code="fs.mount_not_found", severity=FindingSeverity.FAIL, message="x"),
            Finding(code="fs.write_test_failed", severity=FindingSeverity.FAIL, message="x"),
        ]
        assert compute_score(findings) == 0  # 100 - 80 - 60 = -40 → 0


# ── findings_to_verdict ─────────────────────────────────────────────


class TestFindingsToVerdict:
    def test_no_findings_high_confidence_is_pass(self):
        vr = findings_to_verdict([], confidence=Confidence.HIGH)
        assert vr.verdict == Verdict.PASS

    def test_no_findings_low_confidence_is_unknown(self):
        vr = findings_to_verdict([], confidence=Confidence.LOW)
        assert vr.verdict == Verdict.UNKNOWN

    def test_fail_finding_makes_verdict_fail(self):
        findings = [
            Finding(code="x.fail", severity=FindingSeverity.FAIL, message="bad"),
        ]
        vr = findings_to_verdict(findings, confidence=Confidence.HIGH)
        assert vr.verdict == Verdict.FAIL

    def test_warn_finding_makes_verdict_warning(self):
        findings = [
            Finding(code="x.warn", severity=FindingSeverity.WARN, message="meh"),
        ]
        vr = findings_to_verdict(findings, confidence=Confidence.HIGH)
        assert vr.verdict == Verdict.WARNING

    def test_info_only_is_pass(self):
        findings = [
            Finding(code="x.info", severity=FindingSeverity.INFO, message="ok"),
        ]
        vr = findings_to_verdict(findings, confidence=Confidence.HIGH)
        assert vr.verdict == Verdict.PASS

    def test_fail_beats_warn(self):
        findings = [
            Finding(code="x.warn", severity=FindingSeverity.WARN, message="meh"),
            Finding(code="x.fail", severity=FindingSeverity.FAIL, message="bad"),
        ]
        vr = findings_to_verdict(findings, confidence=Confidence.HIGH)
        assert vr.verdict == Verdict.FAIL

    def test_evidence_missing_recorded(self):
        vr = findings_to_verdict(
            [], evidence_missing=["smartctl"], confidence=Confidence.LOW,
        )
        assert "smartctl" in vr.evidence_missing

    def test_reasoning_populated_for_pass(self):
        vr = findings_to_verdict(
            [], confidence=Confidence.HIGH, check_category="filesystem",
        )
        assert "filesystem" in vr.reasoning

    def test_reasoning_populated_for_fail(self):
        findings = [
            Finding(code="x.fail", severity=FindingSeverity.FAIL, message="bad"),
        ]
        vr = findings_to_verdict(findings, confidence=Confidence.HIGH)
        assert "failure" in vr.reasoning


# ── verdict_to_check_result ──────────────────────────────────────────


class TestVerdictToCheckResult:
    def _make_vr(self, verdict=Verdict.PASS, confidence=Confidence.HIGH, score=100):
        return VerdictResult(
            verdict=verdict, confidence=confidence, score=score,
            findings=[], evidence_missing=[], reasoning="test",
        )

    def test_pass_maps_to_ok(self):
        cr = verdict_to_check_result("Test", self._make_vr(Verdict.PASS))
        assert cr.status == Severity.OK

    def test_warning_maps_to_warning(self):
        cr = verdict_to_check_result("Test", self._make_vr(Verdict.WARNING))
        assert cr.status == Severity.WARNING

    def test_fail_maps_to_critical(self):
        cr = verdict_to_check_result("Test", self._make_vr(Verdict.FAIL))
        assert cr.status == Severity.CRITICAL

    def test_unknown_maps_to_unknown(self):
        cr = verdict_to_check_result("Test", self._make_vr(Verdict.UNKNOWN))
        assert cr.status == Severity.UNKNOWN

    def test_details_always_has_verdict_key(self):
        cr = verdict_to_check_result("Test", self._make_vr())
        assert "verdict" in cr.details
        assert "confidence" in cr.details
        assert "health_score" in cr.details
        assert "findings" in cr.details
        assert "evidence_missing" in cr.details

    def test_extra_details_merged(self):
        cr = verdict_to_check_result(
            "Test", self._make_vr(),
            extra_details={"mount_point": "/mnt/data"},
        )
        assert cr.details["mount_point"] == "/mnt/data"

    def test_findings_serialized_in_details(self):
        vr = VerdictResult(
            verdict=Verdict.FAIL, confidence=Confidence.HIGH, score=40,
            findings=[Finding(
                code="x.fail", severity=FindingSeverity.FAIL,
                message="test fail", evidence={"count": 5},
            )],
            evidence_missing=[], reasoning="1 failure",
        )
        cr = verdict_to_check_result("Test", vr)
        assert len(cr.details["findings"]) == 1
        assert cr.details["findings"][0]["code"] == "x.fail"
        assert cr.details["findings"][0]["evidence"]["count"] == 5

    def test_recommendations_generated(self):
        cr = verdict_to_check_result("Test", self._make_vr(Verdict.PASS))
        assert len(cr.recommendations) > 0

    def test_check_name_preserved(self):
        cr = verdict_to_check_result("MyCheck", self._make_vr())
        assert cr.check_name == "MyCheck"


# ── _build_recommendations ───────────────────────────────────────────


class TestBuildRecommendations:
    def test_critical_mentions_backup(self):
        recs = _build_recommendations(Severity.CRITICAL)
        assert any("back up" in r.lower() for r in recs)

    def test_warning_mentions_monitor(self):
        recs = _build_recommendations(Severity.WARNING)
        assert any("30 days" in r for r in recs)

    def test_ok_is_reassuring(self):
        recs = _build_recommendations(Severity.OK)
        assert any("no action" in r.lower() for r in recs)

    def test_unknown_mentions_signals(self):
        recs = _build_recommendations(Severity.UNKNOWN)
        assert any("signal" in r.lower() or "assess" in r.lower() for r in recs)

    def test_target_included_when_provided(self):
        recs = _build_recommendations(Severity.OK, target="/mnt/data")
        assert any("/mnt/data" in r for r in recs)
