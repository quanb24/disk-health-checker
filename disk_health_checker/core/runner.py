from __future__ import annotations

import logging
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
from ..checks.filesystem import run_filesystem_check
from ..checks.surface import run_surface_scan
from ..checks.stress import run_stress_test
from ..checks.integrity import run_integrity_check
from ..verdict import compute_global_verdict

logger = logging.getLogger(__name__)


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
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("SMART check failed")
        results.append(
            CheckResult(
                check_name="SMART",
                status=Severity.UNKNOWN,
                summary=f"SMART check failed: {exc}",
                details={
                    "verdict": "UNKNOWN", "confidence": "LOW",
                    "findings": [], "evidence_missing": ["smart_data"],
                },
            )
        )

    # Filesystem
    try:
        fs_cfg = FsConfig(mount_point=mount_point)
        results.append(run_filesystem_check(fs_cfg, global_config))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Filesystem check failed")
        results.append(
            CheckResult(
                check_name="Filesystem",
                status=Severity.UNKNOWN,
                summary=f"Filesystem check failed: {exc}",
                details={
                    "verdict": "UNKNOWN", "confidence": "LOW",
                    "findings": [], "evidence_missing": ["filesystem"],
                },
            )
        )

    # Surface
    try:
        surf_cfg = SurfaceScanConfig(device=device, quick=quick_surface)
        results.append(run_surface_scan(surf_cfg, global_config))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Surface scan failed")
        results.append(
            CheckResult(
                check_name="SurfaceScan",
                status=Severity.UNKNOWN,
                summary=f"Surface scan failed: {exc}",
                details={
                    "verdict": "UNKNOWN", "confidence": "LOW",
                    "findings": [], "evidence_missing": ["surface_scan"],
                },
            )
        )

    # Stress
    try:
        stress_cfg = StressConfig(mount_point=mount_point)
        results.append(run_stress_test(stress_cfg, global_config))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Stress test failed")
        results.append(
            CheckResult(
                check_name="StressTest",
                status=Severity.UNKNOWN,
                summary=f"Stress test failed: {exc}",
                details={
                    "verdict": "UNKNOWN", "confidence": "LOW",
                    "findings": [], "evidence_missing": ["stress_test"],
                },
            )
        )

    # Integrity
    try:
        integ_cfg = IntegrityConfig(mount_point=mount_point)
        results.append(run_integrity_check(integ_cfg, global_config))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Integrity check failed")
        results.append(
            CheckResult(
                check_name="Integrity",
                status=Severity.UNKNOWN,
                summary=f"Integrity check failed: {exc}",
                details={
                    "verdict": "UNKNOWN", "confidence": "LOW",
                    "findings": [], "evidence_missing": ["integrity"],
                },
            )
        )

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
