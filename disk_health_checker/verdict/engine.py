"""Global verdict engine — combines per-check results into one assessment.

This module is the single place where the question "Is this drive safe
to use overall?" gets answered.  It collects findings from every check
that was run, detects cross-check conflicts, and produces a
``GlobalVerdict`` with health, urgency, usage, confidence, and reasoning.

Design rules:
  1. The verdict is driven by the *worst signal across all checks*.
  2. Conflicts between checks (e.g. SMART OK but surface FAIL) are
     detected and reported — they worsen the assessment.
  3. Missing data (checks not run, SMART unavailable) downgrades
     confidence, never silently improves the verdict.
  4. The engine NEVER returns "Healthy" when any FAIL finding exists
     or when confidence is LOW.
  5. This module does no I/O. It is a pure function of CheckResults.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..models.results import CheckResult, Severity
from .types import (
    ConflictNote,
    GlobalConfidence,
    GlobalVerdict,
    OverallHealth,
    RecommendedUsage,
    Urgency,
)


# ── Finding extraction ──────────────────────────────────────────────


def _extract_findings(cr: CheckResult) -> List[Dict[str, Any]]:
    """Pull structured findings from a CheckResult's details dict."""
    raw = cr.details.get("findings", [])
    tagged: List[Dict[str, Any]] = []
    for f in raw:
        tagged.append({
            "check": cr.check_name,
            "code": f.get("code", ""),
            "severity": f.get("severity", "INFO"),
            "message": f.get("message", ""),
            "evidence": f.get("evidence", {}),
        })
    return tagged


def _extract_verdict(cr: CheckResult) -> str:
    """Get the per-check verdict string, or derive it from status."""
    v = cr.details.get("verdict")
    if v:
        return v
    # Fallback for checks that don't use the unified pipeline (e.g.
    # the macOS self-test capability stub).
    return {
        Severity.OK: "PASS",
        Severity.WARNING: "WARNING",
        Severity.CRITICAL: "FAIL",
        Severity.UNKNOWN: "UNKNOWN",
    }.get(cr.status, "UNKNOWN")


def _extract_confidence(cr: CheckResult) -> str:
    return cr.details.get("confidence", "LOW")


# ── Conflict detection ──────────────────────────────────────────────

# Check names that carry the most diagnostic weight.
_CRITICAL_CHECKS = {"SMART", "SurfaceScan"}


def _detect_conflicts(
    check_verdicts: Dict[str, str],
) -> List[ConflictNote]:
    """Find disagreements between checks that indicate ambiguity.

    We flag when one check says PASS and another says FAIL (or vice
    versa).  Same-direction results (both WARN, both FAIL) are not
    conflicts — they reinforce each other.
    """
    conflicts: List[ConflictNote] = []
    names = list(check_verdicts.keys())

    for i, name_a in enumerate(names):
        for name_b in names[i + 1 :]:
            va = check_verdicts[name_a]
            vb = check_verdicts[name_b]

            # Only flag cross-direction: one PASS and one FAIL/WARNING,
            # or one FAIL and one PASS.
            a_ok = va == "PASS"
            b_ok = vb == "PASS"
            a_bad = va in ("FAIL", "WARNING")
            b_bad = vb in ("FAIL", "WARNING")

            if a_ok and b_bad:
                conflicts.append(ConflictNote(
                    check_a=name_a, verdict_a=va,
                    check_b=name_b, verdict_b=vb,
                    explanation=(
                        f"{name_a} reports healthy but {name_b} found "
                        f"issues ({vb}). This inconsistency suggests the "
                        f"drive may have problems not captured by {name_a}."
                    ),
                ))
            elif b_ok and a_bad:
                conflicts.append(ConflictNote(
                    check_a=name_a, verdict_a=va,
                    check_b=name_b, verdict_b=vb,
                    explanation=(
                        f"{name_b} reports healthy but {name_a} found "
                        f"issues ({va}). This inconsistency warrants "
                        f"further investigation."
                    ),
                ))

    return conflicts


# ── Core engine ─────────────────────────────────────────────────────


def compute_global_verdict(check_results: List[CheckResult]) -> GlobalVerdict:
    """Produce a single global assessment from all per-check results.

    Args:
        check_results: The list of CheckResults from a suite run.
            Each must have details with the unified schema (verdict,
            confidence, findings, evidence_missing).

    Returns:
        A GlobalVerdict answering "Is this drive safe to use?"
    """
    if not check_results:
        return GlobalVerdict(
            health=OverallHealth.UNKNOWN,
            urgency=Urgency.MONITOR,
            usage=RecommendedUsage.NON_CRITICAL,
            confidence=GlobalConfidence.LOW,
            reasoning="No checks were run. Cannot assess drive health.",
            composite_score=0,
        )

    # ── Gather data from all checks ──
    all_findings: List[Dict[str, Any]] = []
    check_verdicts: Dict[str, str] = {}
    check_confidences: Dict[str, str] = {}
    all_evidence_missing: List[str] = []

    for cr in check_results:
        findings = _extract_findings(cr)
        all_findings.extend(findings)
        check_verdicts[cr.check_name] = _extract_verdict(cr)
        check_confidences[cr.check_name] = _extract_confidence(cr)
        missing = cr.details.get("evidence_missing", [])
        for m in missing:
            tagged = f"{cr.check_name}:{m}"
            if tagged not in all_evidence_missing:
                all_evidence_missing.append(tagged)

    # ── Count severities ──
    fail_findings = [f for f in all_findings if f["severity"] == "FAIL"]
    warn_findings = [f for f in all_findings if f["severity"] == "WARN"]
    info_findings = [f for f in all_findings if f["severity"] == "INFO"]

    fail_count = len(fail_findings)
    warn_count = len(warn_findings)

    # ── Identify which checks failed/warned ──
    checks_with_fail = {
        f["check"] for f in fail_findings
    }
    checks_with_warn = {
        f["check"] for f in warn_findings
    }

    # SMART is the most important signal for drive health.
    smart_verdict = check_verdicts.get("SMART", None)
    smart_ran = smart_verdict is not None
    smart_failed = smart_verdict == "FAIL"
    smart_warned = smart_verdict == "WARNING"
    smart_unknown = smart_verdict == "UNKNOWN"
    smart_passed = smart_verdict == "PASS"

    # ── Detect conflicts ──
    # Only consider checks that actually produced findings (skip stubs).
    real_verdicts = {
        name: v for name, v in check_verdicts.items()
        if v != "UNKNOWN" or name in _CRITICAL_CHECKS
    }
    conflicts = _detect_conflicts(real_verdicts)

    # ── Compute global confidence ──
    confidence = _compute_confidence(
        check_confidences, smart_ran, len(check_results),
    )

    # ── Determine health level ──
    health = _determine_health(
        fail_count=fail_count,
        warn_count=warn_count,
        smart_failed=smart_failed,
        smart_warned=smart_warned,
        smart_unknown=smart_unknown,
        smart_ran=smart_ran,
        checks_with_fail=checks_with_fail,
        conflicts=conflicts,
        confidence=confidence,
    )

    # ── Map health to urgency and usage ──
    urgency = _health_to_urgency(health)
    usage = _health_to_usage(health)

    # ── Composite score (advisory) ──
    composite_score = _compute_composite_score(check_results)

    # ── Key findings (the ones that most influenced the verdict) ──
    key_findings = _select_key_findings(fail_findings, warn_findings)

    # ── Build reasoning ──
    reasoning = _build_reasoning(
        health=health,
        confidence=confidence,
        fail_count=fail_count,
        warn_count=warn_count,
        checks_with_fail=checks_with_fail,
        checks_with_warn=checks_with_warn,
        smart_verdict=smart_verdict,
        conflicts=conflicts,
        all_evidence_missing=all_evidence_missing,
        total_checks=len(check_results),
    )

    return GlobalVerdict(
        health=health,
        urgency=urgency,
        usage=usage,
        confidence=confidence,
        all_findings=all_findings,
        key_findings=key_findings,
        conflicts=conflicts,
        check_verdicts=check_verdicts,
        reasoning=reasoning,
        composite_score=composite_score,
    )


# ── Confidence computation ──────────────────────────────────────────


def _compute_confidence(
    check_confidences: Dict[str, str],
    smart_ran: bool,
    total_checks: int,
) -> GlobalConfidence:
    """Determine how trustworthy the global verdict is.

    Rules:
    - If SMART didn't run or has LOW confidence → global is at most MEDIUM.
    - If majority of checks have LOW confidence → LOW.
    - If only one check ran → at most MEDIUM.
    """
    if total_checks == 0:
        return GlobalConfidence.LOW

    confidences = list(check_confidences.values())
    low_count = sum(1 for c in confidences if c == "LOW")
    high_count = sum(1 for c in confidences if c == "HIGH")

    # Single check can't give global HIGH — we need breadth.
    if total_checks == 1:
        if confidences[0] == "HIGH":
            return GlobalConfidence.MEDIUM
        return GlobalConfidence.LOW

    # SMART is the backbone of drive health assessment.
    smart_conf = check_confidences.get("SMART")
    if not smart_ran:
        # No SMART at all — cap at MEDIUM.
        if high_count >= total_checks // 2:
            return GlobalConfidence.MEDIUM
        return GlobalConfidence.LOW

    if smart_conf == "LOW":
        return GlobalConfidence.LOW

    # Majority LOW → LOW.
    if low_count > total_checks // 2:
        return GlobalConfidence.LOW

    # SMART HIGH + at least one other HIGH → HIGH.
    if smart_conf == "HIGH" and high_count >= 2:
        return GlobalConfidence.HIGH

    return GlobalConfidence.MEDIUM


# ── Health determination ────────────────────────────────────────────


def _determine_health(
    *,
    fail_count: int,
    warn_count: int,
    smart_failed: bool,
    smart_warned: bool,
    smart_unknown: bool,
    smart_ran: bool,
    checks_with_fail: set[str],
    conflicts: List[ConflictNote],
    confidence: GlobalConfidence,
) -> OverallHealth:
    """Map the aggregated signals to a health level.

    Priority order (checked top-to-bottom, first match wins):
    """
    # ── FAILING: SMART failure, or failures in multiple checks ──
    if smart_failed:
        return OverallHealth.FAILING

    if fail_count > 0 and len(checks_with_fail) >= 2:
        return OverallHealth.FAILING

    # ── AT RISK: failure in any single check ──
    if fail_count > 0:
        return OverallHealth.AT_RISK

    # ── DEGRADING: SMART warning + warnings elsewhere, or conflicts ──
    if smart_warned and warn_count > 1:
        return OverallHealth.DEGRADING

    if conflicts and warn_count > 0:
        return OverallHealth.DEGRADING

    # ── WATCH: any warnings present ──
    if warn_count > 0:
        return OverallHealth.WATCH

    # ── UNKNOWN: can't determine (no SMART, low confidence) ──
    if confidence == GlobalConfidence.LOW:
        return OverallHealth.UNKNOWN

    if smart_unknown:
        return OverallHealth.UNKNOWN

    # ── HEALTHY: no issues, adequate confidence ──
    return OverallHealth.HEALTHY


# ── Health → urgency / usage mapping ────────────────────────────────


def _health_to_urgency(health: OverallHealth) -> Urgency:
    return {
        OverallHealth.HEALTHY: Urgency.NO_ACTION,
        OverallHealth.WATCH: Urgency.MONITOR,
        OverallHealth.DEGRADING: Urgency.RECHECK_SOON,
        OverallHealth.AT_RISK: Urgency.BACKUP_NOW,
        OverallHealth.FAILING: Urgency.REPLACE_NOW,
        OverallHealth.UNKNOWN: Urgency.MONITOR,
    }[health]


def _health_to_usage(health: OverallHealth) -> RecommendedUsage:
    return {
        OverallHealth.HEALTHY: RecommendedUsage.PRIMARY,
        OverallHealth.WATCH: RecommendedUsage.SECONDARY,
        OverallHealth.DEGRADING: RecommendedUsage.NON_CRITICAL,
        OverallHealth.AT_RISK: RecommendedUsage.BACKUP_ONLY,
        OverallHealth.FAILING: RecommendedUsage.DO_NOT_TRUST,
        OverallHealth.UNKNOWN: RecommendedUsage.NON_CRITICAL,
    }[health]


# ── Composite score ─────────────────────────────────────────────────


def _compute_composite_score(check_results: List[CheckResult]) -> int:
    """Average the per-check scores, weighted by check importance.

    SMART is weighted 3x because it's the primary health signal.
    All other checks are weighted 1x.
    """
    if not check_results:
        return 0

    total_weight = 0
    weighted_sum = 0

    for cr in check_results:
        score = cr.details.get("health_score")
        if score is None:
            continue
        weight = 3 if cr.check_name == "SMART" else 1
        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0:
        return 0

    return max(0, min(100, round(weighted_sum / total_weight)))


# ── Key findings selection ──────────────────────────────────────────


def _select_key_findings(
    fail_findings: List[Dict[str, Any]],
    warn_findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Pick the findings that most influenced the verdict.

    All FAIL findings are key. For WARN, take the first 3 (most
    important — they come from the checks in order).
    """
    key: List[Dict[str, Any]] = list(fail_findings)
    remaining_slots = max(0, 5 - len(key))
    key.extend(warn_findings[:remaining_slots])
    return key


# ── Reasoning builder ───────────────────────────────────────────────


def _build_reasoning(
    *,
    health: OverallHealth,
    confidence: GlobalConfidence,
    fail_count: int,
    warn_count: int,
    checks_with_fail: set[str],
    checks_with_warn: set[str],
    smart_verdict: str | None,
    conflicts: List[ConflictNote],
    all_evidence_missing: List[str],
    total_checks: int,
) -> str:
    """Build a human-readable explanation of the global verdict."""
    parts: List[str] = []

    # Lead with the headline.
    parts.append(f"Overall health: {health.value}.")

    # Describe what drove this verdict.
    if health == OverallHealth.HEALTHY:
        parts.append(
            f"All {total_checks} check(s) passed with no warnings."
        )
    elif health == OverallHealth.FAILING:
        if smart_verdict == "FAIL":
            parts.append(
                "SMART diagnostics indicate the drive is failing. "
                "This is the drive's own firmware reporting a critical problem."
            )
        else:
            parts.append(
                f"Critical failures detected in {len(checks_with_fail)} "
                f"check(s): {', '.join(sorted(checks_with_fail))}."
            )
    elif health == OverallHealth.AT_RISK:
        parts.append(
            f"{fail_count} failure(s) found in: "
            f"{', '.join(sorted(checks_with_fail))}."
        )
    elif health == OverallHealth.DEGRADING:
        parts.append(
            f"Multiple warning signals across checks: "
            f"{', '.join(sorted(checks_with_warn))}."
        )
    elif health == OverallHealth.WATCH:
        parts.append(
            f"{warn_count} warning(s) detected in: "
            f"{', '.join(sorted(checks_with_warn))}. "
            f"No critical issues, but worth monitoring."
        )
    elif health == OverallHealth.UNKNOWN:
        if smart_verdict == "UNKNOWN":
            parts.append(
                "SMART data could not be read. Drive health cannot be "
                "reliably determined without SMART diagnostics."
            )
        else:
            parts.append(
                "Insufficient data to confidently assess drive health."
            )

    # Mention conflicts.
    if conflicts:
        conflict_descs = [c.explanation for c in conflicts]
        parts.append(
            f"Cross-check conflict(s) detected: {'; '.join(conflict_descs)}"
        )

    # Mention confidence.
    if confidence != GlobalConfidence.HIGH:
        parts.append(f"Confidence is {confidence.value}.")
        if all_evidence_missing:
            parts.append(
                f"Missing signals: {', '.join(all_evidence_missing[:5])}."
            )

    return " ".join(parts)
