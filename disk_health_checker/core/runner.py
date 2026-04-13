from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from typing import List

from ..models.config import (
    GlobalConfig,
    SmartConfig,
    FsConfig,
    SurfaceScanConfig,
    StressConfig,
    IntegrityConfig,
)
from ..models.results import CheckResult, SuiteResult, Severity
from ..checks.smart import run_smart_check
from ..checks.smart.errors import SmartctlError
from ..checks.filesystem import run_filesystem_check
from ..checks.surface import run_surface_scan
from ..checks.stress import run_stress_test
from ..checks.integrity import run_integrity_check
from ..verdict import compute_global_verdict

logger = logging.getLogger(__name__)

# Exception types that represent expected operational failures (I/O,
# subprocess, SMART hardware issues).  Everything else is a bug.
_EXPECTED_ERRORS = (SmartctlError, OSError, subprocess.SubprocessError, ValueError, KeyError)


def _error_check_result(
    check_name: str, exc: Exception, evidence_key: str,
) -> CheckResult:
    """Build a standardised UNKNOWN CheckResult for a failed check."""
    return CheckResult(
        check_name=check_name,
        status=Severity.UNKNOWN,
        summary=f"{check_name} check failed: {exc}",
        details={
            "verdict": "UNKNOWN",
            "confidence": "LOW",
            "health_score": 50,
            "findings": [],
            "evidence_missing": [evidence_key],
            "internal_error": type(exc).__name__,
        },
    )


def aggregate_status(results: List[CheckResult]) -> Severity:
    """
    Aggregate individual check severities into a single overall status.

    Priority order (highest to lowest):
      CRITICAL > WARNING > UNKNOWN > OK
    """
    priority = {
        Severity.OK: 0,
        Severity.UNKNOWN: 1,
        Severity.WARNING: 2,
        Severity.CRITICAL: 3,
    }
    worst = Severity.OK
    worst_score = priority[worst]

    for r in results:
        score = priority.get(r.status, 0)
        if score > worst_score:
            worst = r.status
            worst_score = score
            if worst is Severity.CRITICAL:
                break

    return worst


def run_full_suite(
    device: str,
    mount_point: str,
    global_config: GlobalConfig,
    quick_surface: bool = True,
) -> SuiteResult:
    started = datetime.now(timezone.utc)
    results: List[CheckResult] = []

    # SMART
    try:
        smart_cfg = SmartConfig(device=device)
        results.append(run_smart_check(smart_cfg))
    except _EXPECTED_ERRORS as exc:  # pragma: no cover - defensive
        logger.exception("SMART check failed")
        results.append(_error_check_result("SMART", exc, "smart_data"))

    # Filesystem
    try:
        fs_cfg = FsConfig(mount_point=mount_point)
        results.append(run_filesystem_check(fs_cfg, global_config))
    except _EXPECTED_ERRORS as exc:  # pragma: no cover - defensive
        logger.exception("Filesystem check failed")
        results.append(_error_check_result("Filesystem", exc, "filesystem"))

    # Surface
    try:
        surf_cfg = SurfaceScanConfig(device=device, quick=quick_surface)
        results.append(run_surface_scan(surf_cfg, global_config))
    except _EXPECTED_ERRORS as exc:  # pragma: no cover - defensive
        logger.exception("Surface scan failed")
        results.append(_error_check_result("SurfaceScan", exc, "surface_scan"))

    # Stress — requires destructive mode
    if global_config.non_destructive:
        logger.info("Skipping stress test (non-destructive mode)")
        results.append(
            CheckResult(
                check_name="StressTest",
                status=Severity.UNKNOWN,
                summary="Skipped — non-destructive mode active.",
                details={
                    "verdict": "UNKNOWN", "confidence": "LOW",
                    "health_score": 50,
                    "findings": [], "evidence_missing": ["stress_test"],
                    "reason": "non_destructive_mode",
                },
                recommendations=[
                    "Re-run with --allow-destructive to enable stress testing.",
                ],
            )
        )
    else:
        try:
            stress_cfg = StressConfig(mount_point=mount_point)
            results.append(run_stress_test(stress_cfg, global_config))
        except _EXPECTED_ERRORS as exc:  # pragma: no cover - defensive
            logger.exception("Stress test failed")
            results.append(_error_check_result("StressTest", exc, "stress_test"))

    # Integrity — requires destructive mode
    if global_config.non_destructive:
        logger.info("Skipping integrity check (non-destructive mode)")
        results.append(
            CheckResult(
                check_name="Integrity",
                status=Severity.UNKNOWN,
                summary="Skipped — non-destructive mode active.",
                details={
                    "verdict": "UNKNOWN", "confidence": "LOW",
                    "health_score": 50,
                    "findings": [], "evidence_missing": ["integrity"],
                    "reason": "non_destructive_mode",
                },
                recommendations=[
                    "Re-run with --allow-destructive to enable integrity testing.",
                ],
            )
        )
    else:
        try:
            integ_cfg = IntegrityConfig(mount_point=mount_point)
            results.append(run_integrity_check(integ_cfg, global_config))
        except _EXPECTED_ERRORS as exc:  # pragma: no cover - defensive
            logger.exception("Integrity check failed")
            results.append(_error_check_result("Integrity", exc, "integrity"))

    finished = datetime.now(timezone.utc)
    overall = aggregate_status(results)
    gv = compute_global_verdict(results)

    return SuiteResult(
        target=f"device={device}, mount={mount_point}",
        overall_status=overall,
        check_results=results,
        started_at=started,
        finished_at=finished,
        global_verdict=gv,
    )
