"""macOS-first non-destructive validation workflow.

Runs SMART + self-test capability check + filesystem stub, then
produces a global verdict via the verdict engine.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from ..checks.smart import run_smart_check
from ..models.config import GlobalConfig, SmartConfig
from ..models.results import CheckResult, Severity, SuiteResult
from ..verdict import compute_global_verdict
from .runner import aggregate_status

logger = logging.getLogger(__name__)


def run_macos_full_workflow(device: str, global_config: GlobalConfig) -> SuiteResult:
    """macOS non-destructive workflow: SMART + self-test + fs stub.

    The global verdict engine produces the final recommendation
    (replaces the previous ad-hoc "Overall Recommendation" check).
    """
    started = datetime.now(timezone.utc)
    results: List[CheckResult] = []

    # ── SMART health ──
    smart_cfg = SmartConfig(device=device)
    smart_result = run_smart_check(smart_cfg)
    results.append(smart_result)

    supports_self_test = bool(smart_result.details.get("supports_self_test"))

    # ── Self-test capability ──
    if supports_self_test:
        summary = (
            "Drive supports SMART self-tests. "
            "Running a long self-test is recommended for deeper validation."
        )
        recommendations = [
            f"Run a long self-test with: smartctl -t long {device}",
            "Review the self-test log after completion for any errors.",
        ]
    else:
        summary = "Could not confirm SMART self-test support from drive data."
        recommendations = [
            f"Attempt to run a long self-test with: smartctl -t long {device}",
            "If the command fails, the enclosure or drive firmware may not support self-tests.",
        ]

    if smart_result.status == Severity.CRITICAL:
        self_test_status = Severity.CRITICAL
    elif smart_result.status == Severity.UNKNOWN:
        self_test_status = Severity.UNKNOWN
    else:
        self_test_status = Severity.OK if supports_self_test else Severity.UNKNOWN

    self_test_check = CheckResult(
        check_name="SMART Self-Test Capability",
        status=self_test_status,
        summary=summary,
        details={
            "supports_self_test": supports_self_test,
            "verdict": "PASS" if supports_self_test else "UNKNOWN",
            "confidence": "MEDIUM",
            "health_score": 100 if supports_self_test else 50,
            "findings": [],
            "evidence_missing": [] if supports_self_test else ["self_test_support"],
        },
        recommendations=recommendations,
    )
    results.append(self_test_check)

    # ── Filesystem verification stub ──
    fs_stub = CheckResult(
        check_name="Filesystem (macOS stub)",
        status=Severity.UNKNOWN,
        summary="Filesystem verification on macOS is not automated by this tool.",
        details={
            "verdict": "UNKNOWN",
            "confidence": "LOW",
            "health_score": 50,
            "findings": [],
            "evidence_missing": ["filesystem_verification"],
        },
        recommendations=[
            "To verify a volume, run: diskutil verifyVolume /dev/diskXsY",
            "For APFS containers, see: diskutil apfs list",
        ],
    )
    results.append(fs_stub)

    finished = datetime.now(timezone.utc)
    overall = aggregate_status(results)
    gv = compute_global_verdict(results)

    return SuiteResult(
        target=f"device={device}",
        overall_status=overall,
        check_results=results,
        started_at=started,
        finished_at=finished,
        global_verdict=gv,
    )
