"""Shared evaluation utilities for all check types.

Every check — SMART, filesystem, surface, stress, integrity — produces
a list of ``Finding`` objects and feeds them through this module to get
a ``VerdictResult`` and a ``CheckResult``.  This is the **single source
of truth** for verdict determination, confidence gating, score
calculation, and recommendation generation.

Design rules:
- Verdict is determined by the worst finding severity, NOT by score.
- Score is advisory (0-100). Deductions are driven by per-code weights.
- Confidence reflects how much of the evidence floor was readable.
- A PASS verdict requires at least MEDIUM confidence.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models.results import CheckResult, Severity
from ..models.smart_types import (
    Confidence,
    Finding,
    FindingSeverity,
    Verdict,
    VerdictResult,
)

# ── Verdict ↔ Severity mapping ──────────────────────────────────────

_VERDICT_TO_SEVERITY: dict[Verdict, Severity] = {
    Verdict.PASS: Severity.OK,
    Verdict.WARNING: Severity.WARNING,
    Verdict.FAIL: Severity.CRITICAL,
    Verdict.UNKNOWN: Severity.UNKNOWN,
}


# ── Default score weights (per finding code) ────────────────────────
# Checks may supply their own weights; these are the global defaults.

_DEFAULT_WEIGHTS: dict[str, int] = {
    # -- filesystem --
    "fs.mount_not_found": 80,
    "fs.write_test_failed": 60,
    "fs.fsck_skipped": 0,
    # -- surface --
    "surface.device_not_found": 80,
    "surface.read_errors": 60,
    "surface.slow_blocks": 20,
    "surface.access_denied": 0,
    # -- stress --
    "stress.target_not_found": 80,
    "stress.io_errors": 60,
    "stress.no_ops_completed": 30,
    "stress.insufficient_space": 20,
    # -- integrity --
    "integrity.target_not_found": 80,
    "integrity.pattern_mismatch": 60,
    "integrity.manifest_mismatch": 30,
    "integrity.manifest_missing_files": 20,
}


# ── Core pipeline functions ─────────────────────────────────────────


def compute_score(
    findings: List[Finding],
    weights: Optional[dict[str, int]] = None,
    base: int = 100,
) -> int:
    """Compute an advisory 0-100 score by deducting per-finding weights."""
    w = weights or _DEFAULT_WEIGHTS
    score = base
    for f in findings:
        score -= w.get(f.code, 0)
    return max(0, min(100, score))


def findings_to_verdict(
    findings: List[Finding],
    *,
    evidence_missing: Optional[List[str]] = None,
    confidence: Confidence = Confidence.HIGH,
    weights: Optional[dict[str, int]] = None,
    check_category: str = "",
) -> VerdictResult:
    """Derive a VerdictResult from a list of findings.

    Args:
        findings: All observations produced by the check.
        evidence_missing: Signal names the check wanted but couldn't read.
        confidence: How complete the evidence was.
        weights: Per-code score deductions (defaults to _DEFAULT_WEIGHTS).
        check_category: Human label for reasoning (e.g. "filesystem").
    """
    evidence_missing = evidence_missing or []
    score = compute_score(findings, weights)

    has_fail = any(f.severity == FindingSeverity.FAIL for f in findings)
    has_warn = any(f.severity == FindingSeverity.WARN for f in findings)

    if has_fail:
        verdict = Verdict.FAIL
    elif has_warn:
        verdict = Verdict.WARNING
    elif confidence == Confidence.LOW:
        verdict = Verdict.UNKNOWN
    else:
        verdict = Verdict.PASS

    # Build reasoning
    label = check_category or "check"
    if verdict == Verdict.PASS:
        reasoning = f"No significant {label} issues detected."
    elif verdict == Verdict.UNKNOWN:
        missing_str = ", ".join(evidence_missing) if evidence_missing else "unknown"
        reasoning = f"Insufficient data for {label}. Missing: {missing_str}."
    else:
        fail_count = sum(1 for f in findings if f.severity == FindingSeverity.FAIL)
        warn_count = sum(1 for f in findings if f.severity == FindingSeverity.WARN)
        parts = []
        if fail_count:
            parts.append(f"{fail_count} failure(s)")
        if warn_count:
            parts.append(f"{warn_count} warning(s)")
        reasoning = f"{', '.join(parts)} detected."

    return VerdictResult(
        verdict=verdict,
        confidence=confidence,
        score=score,
        findings=findings,
        evidence_missing=evidence_missing,
        reasoning=reasoning,
    )


def verdict_to_check_result(
    check_name: str,
    vr: VerdictResult,
    *,
    extra_details: Optional[Dict[str, Any]] = None,
    target_description: str = "",
) -> CheckResult:
    """Convert a VerdictResult into a CheckResult for CLI/JSON transport.

    This is the single conversion point. All checks use this function
    so that CheckResult.details always has a consistent schema.
    """
    severity = _VERDICT_TO_SEVERITY[vr.verdict]

    details: Dict[str, Any] = {
        "verdict": vr.verdict.value,
        "confidence": vr.confidence.value,
        "health_score": vr.score,
        "findings": [
            {
                "code": f.code,
                "severity": f.severity.value,
                "message": f.message,
                "evidence": f.evidence,
            }
            for f in vr.findings
        ],
        "evidence_missing": vr.evidence_missing,
    }

    if extra_details:
        details.update(extra_details)

    # Build summary
    first_finding = (
        vr.findings[0].message.split(".")[0] if vr.findings else vr.reasoning.split(".")[0]
    )
    summary = f"{vr.verdict.value} (score {vr.score}/100). {first_finding}."

    # Build recommendations
    recommendations = _build_recommendations(severity, target_description)

    return CheckResult(
        check_name=check_name,
        status=severity,
        summary=summary,
        details=details,
        recommendations=recommendations,
    )


def _build_recommendations(severity: Severity, target: str = "") -> list[str]:
    """Generate standard recommendations based on severity."""
    suffix = f" ({target})" if target else ""
    if severity == Severity.CRITICAL:
        return [
            f"Back up data immediately{suffix}.",
            "Investigate the failures listed above and consider replacing the hardware.",
        ]
    if severity == Severity.WARNING:
        return [
            f"Keep backups current{suffix}. Warning signs detected.",
            "Re-run this check in ~30 days to monitor for progression.",
        ]
    if severity == Severity.OK:
        return [f"No action needed{suffix}. Keep regular backups as always."]
    # UNKNOWN
    return [f"Could not fully assess health{suffix}. See signals missing above."]
