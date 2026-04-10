from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from ..checks.smart import run_smart_check
from ..models.config import GlobalConfig, SmartConfig
from ..models.results import CheckResult, Severity, SuiteResult

logger = logging.getLogger(__name__)


def run_macos_full_workflow(device: str, global_config: GlobalConfig) -> SuiteResult:
    """
    macOS-first, non-destructive validation workflow:

    - SMART health assessment
    - SMART self-test capability check and long-test recommendation
    - Filesystem verification stub (recommend diskutil verifyVolume)
    - Final human-friendly recommendation: SAFE TO USE / USE WITH CAUTION / DO NOT TRUST
    """
    started = datetime.now(timezone.utc)
    results: List[CheckResult] = []

    # SMART health
    smart_cfg = SmartConfig(device=device)
    smart_result = run_smart_check(smart_cfg)
    results.append(smart_result)

    health_state = smart_result.details.get("health_state", "UNKNOWN")
    health_score = smart_result.details.get("health_score")
    supports_self_test = bool(smart_result.details.get("supports_self_test"))

    # Self-test capability and recommendation
    if supports_self_test:
        summary = "Drive supports SMART self-tests. Running a long self-test is recommended for deeper validation."
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

    # Status for self-test capability:
    # - If the drive is already failing, keep CRITICAL.
    # - If SMART data is unknown, mark capability as UNKNOWN.
    # - Otherwise, treat as OK (capable) or UNKNOWN (not confirmed).
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
        details={"supports_self_test": supports_self_test},
        recommendations=recommendations,
    )
    results.append(self_test_check)

    # Filesystem verification stub for macOS
    fs_stub = CheckResult(
        check_name="Filesystem (macOS stub)",
        status=Severity.UNKNOWN,
        summary="Filesystem verification on macOS is not automated by this tool.",
        details={},
        recommendations=[
            "To verify a volume, run: diskutil verifyVolume /dev/diskXsY (replace with the correct volume identifier).",
            "For APFS containers, see: diskutil apfs list and diskutil verifyVolume for APFS volumes.",
        ],
    )
    results.append(fs_stub)

    # Final recommendation — derived from the verdict produced by the
    # evaluation pipeline, not from a parallel re-interpretation.
    verdict = smart_result.details.get("verdict", "UNKNOWN")
    confidence = smart_result.details.get("confidence", "LOW")

    _VERDICT_MAP = {
        "PASS": ("SAFE TO USE", Severity.OK),
        "WARNING": ("USE WITH CAUTION", Severity.WARNING),
        "FAIL": ("DO NOT TRUST", Severity.CRITICAL),
        "UNKNOWN": ("USE WITH CAUTION (SMART health unknown)", Severity.UNKNOWN),
    }
    final_rec, status = _VERDICT_MAP.get(verdict, _VERDICT_MAP["UNKNOWN"])

    explanation_parts = [
        f"Verdict: {verdict} (confidence: {confidence}).",
    ]
    if health_score is not None:
        explanation_parts.append(f"Health score: {health_score}/100.")
    explanation_parts.append(
        "Always ensure you have current backups before storing important data on this disk."
    )

    final_check = CheckResult(
        check_name="Overall Recommendation",
        status=status,
        summary=f"{final_rec}: " + " ".join(explanation_parts),
        details={
            "final_recommendation": final_rec,
            "verdict": verdict,
            "confidence": confidence,
            "health_state": health_state,
            "health_score": health_score,
        },
        recommendations=[
            "If the drive is marked DO NOT TRUST, replace it as soon as possible.",
            "If marked USE WITH CAUTION, monitor SMART values and avoid using it as sole storage for critical data.",
        ],
    )
    results.append(final_check)

    finished = datetime.now(timezone.utc)

    return SuiteResult(
        target=f"device={device}",
        overall_status=status,
        check_results=results,
        started_at=started,
        finished_at=finished,
    )


