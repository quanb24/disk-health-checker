"""Tests for the full suite runner and aggregate_status."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

from disk_health_checker.core.runner import aggregate_status, run_full_suite
from disk_health_checker.models.config import GlobalConfig
from disk_health_checker.models.results import CheckResult, Severity


# ── aggregate_status ──────────────────────────────────────────────


def _cr(status: Severity) -> CheckResult:
    return CheckResult(
        check_name="Test",
        status=status,
        summary="test",
        details={},
    )


def test_aggregate_all_ok():
    assert aggregate_status([_cr(Severity.OK), _cr(Severity.OK)]) == Severity.OK


def test_aggregate_worst_wins():
    results = [_cr(Severity.OK), _cr(Severity.WARNING), _cr(Severity.OK)]
    assert aggregate_status(results) == Severity.WARNING


def test_aggregate_critical_short_circuits():
    results = [_cr(Severity.CRITICAL), _cr(Severity.OK)]
    assert aggregate_status(results) == Severity.CRITICAL


def test_aggregate_unknown_above_ok():
    results = [_cr(Severity.OK), _cr(Severity.UNKNOWN)]
    assert aggregate_status(results) == Severity.UNKNOWN


def test_aggregate_empty_list():
    assert aggregate_status([]) == Severity.OK


# ── run_full_suite: non-destructive mode ──────────────────────────


def _mock_smart_result():
    return CheckResult(
        check_name="SMART",
        status=Severity.OK,
        summary="PASS",
        details={
            "verdict": "PASS", "confidence": "HIGH",
            "health_score": 100, "findings": [],
            "evidence_missing": [],
        },
    )


def _mock_fs_result():
    return CheckResult(
        check_name="Filesystem",
        status=Severity.OK,
        summary="PASS",
        details={
            "verdict": "PASS", "confidence": "HIGH",
            "health_score": 100, "findings": [],
            "evidence_missing": [],
        },
    )


def _mock_surface_result():
    return CheckResult(
        check_name="SurfaceScan",
        status=Severity.OK,
        summary="PASS",
        details={
            "verdict": "PASS", "confidence": "HIGH",
            "health_score": 100, "findings": [],
            "evidence_missing": [],
        },
    )


@patch("disk_health_checker.core.runner.run_surface_scan", return_value=_mock_surface_result())
@patch("disk_health_checker.core.runner.run_filesystem_check", return_value=_mock_fs_result())
@patch("disk_health_checker.core.runner.run_smart_check", return_value=_mock_smart_result())
def test_non_destructive_skips_stress_integrity(mock_smart, mock_fs, mock_surf):
    """In non-destructive mode, stress and integrity are skipped with UNKNOWN status."""
    cfg = GlobalConfig(non_destructive=True)
    result = run_full_suite("/dev/test", "/mnt/test", cfg)

    # Should have 5 check results
    assert len(result.check_results) == 5
    names = [cr.check_name for cr in result.check_results]
    assert "StressTest" in names
    assert "Integrity" in names

    # Stress and Integrity should be UNKNOWN with skip reason
    stress = next(cr for cr in result.check_results if cr.check_name == "StressTest")
    assert stress.status == Severity.UNKNOWN
    assert stress.details.get("reason") == "non_destructive_mode"
    assert stress.details.get("health_score") == 50

    integrity = next(cr for cr in result.check_results if cr.check_name == "Integrity")
    assert integrity.status == Severity.UNKNOWN
    assert integrity.details.get("reason") == "non_destructive_mode"
    assert integrity.details.get("health_score") == 50

    # SMART, Filesystem, Surface should have been called
    mock_smart.assert_called_once()
    mock_fs.assert_called_once()
    mock_surf.assert_called_once()


@patch("disk_health_checker.core.runner.run_integrity_check")
@patch("disk_health_checker.core.runner.run_stress_test")
@patch("disk_health_checker.core.runner.run_surface_scan", return_value=_mock_surface_result())
@patch("disk_health_checker.core.runner.run_filesystem_check", return_value=_mock_fs_result())
@patch("disk_health_checker.core.runner.run_smart_check", return_value=_mock_smart_result())
def test_destructive_runs_all_checks(mock_smart, mock_fs, mock_surf, mock_stress, mock_integ):
    """In destructive mode (non_destructive=False), all 5 checks run."""
    mock_stress.return_value = CheckResult(
        check_name="StressTest", status=Severity.OK,
        summary="PASS", details={"verdict": "PASS", "confidence": "HIGH",
                                  "health_score": 100, "findings": [], "evidence_missing": []},
    )
    mock_integ.return_value = CheckResult(
        check_name="Integrity", status=Severity.OK,
        summary="PASS", details={"verdict": "PASS", "confidence": "HIGH",
                                  "health_score": 100, "findings": [], "evidence_missing": []},
    )

    cfg = GlobalConfig(non_destructive=False)
    result = run_full_suite("/dev/test", "/mnt/test", cfg)

    assert len(result.check_results) == 5
    mock_stress.assert_called_once()
    mock_integ.assert_called_once()

    # No skipped checks — none should have reason field
    for cr in result.check_results:
        assert cr.details.get("reason") != "non_destructive_mode"


@patch("disk_health_checker.core.runner.run_surface_scan", return_value=_mock_surface_result())
@patch("disk_health_checker.core.runner.run_filesystem_check", return_value=_mock_fs_result())
@patch("disk_health_checker.core.runner.run_smart_check", return_value=_mock_smart_result())
def test_non_destructive_global_verdict_present(mock_smart, mock_fs, mock_surf):
    """Non-destructive run still produces a global verdict."""
    cfg = GlobalConfig(non_destructive=True)
    result = run_full_suite("/dev/test", "/mnt/test", cfg)
    assert result.global_verdict is not None


@patch("disk_health_checker.core.runner.run_surface_scan", return_value=_mock_surface_result())
@patch("disk_health_checker.core.runner.run_filesystem_check", return_value=_mock_fs_result())
@patch("disk_health_checker.core.runner.run_smart_check", return_value=_mock_smart_result())
def test_non_destructive_skipped_checks_have_recommendations(mock_smart, mock_fs, mock_surf):
    """Skipped checks should include a recommendation to re-run with --allow-destructive."""
    cfg = GlobalConfig(non_destructive=True)
    result = run_full_suite("/dev/test", "/mnt/test", cfg)

    stress = next(cr for cr in result.check_results if cr.check_name == "StressTest")
    assert any("--allow-destructive" in r for r in stress.recommendations)

    integrity = next(cr for cr in result.check_results if cr.check_name == "Integrity")
    assert any("--allow-destructive" in r for r in integrity.recommendations)
