"""Data types for the global verdict engine.

These types represent the *final answer* to the user's question:
"Is this drive safe to use?"

They are computed by the engine from the per-check findings — they are
NOT produced by any individual check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class OverallHealth(str, Enum):
    """Drive-level health assessment derived from all checks combined.

    Ordered from best to worst.  The engine picks the level that matches
    the worst signal combination across all checks.
    """
    HEALTHY = "Healthy"
    WATCH = "Watch"
    DEGRADING = "Degrading"
    AT_RISK = "At Risk"
    FAILING = "Failing"
    UNKNOWN = "Unknown"


class Urgency(str, Enum):
    """How urgently the user should act."""
    NO_ACTION = "No action needed"
    MONITOR = "Monitor over time"
    RECHECK_SOON = "Recheck within 30 days"
    BACKUP_NOW = "Backup data now"
    REPLACE_NOW = "Replace drive immediately"


class RecommendedUsage(str, Enum):
    """What this drive is safe for, given its current health."""
    PRIMARY = "Safe for primary use"
    SECONDARY = "Safe for secondary/backup use"
    NON_CRITICAL = "Non-critical storage only"
    BACKUP_ONLY = "Backup target only — do not rely on"
    DO_NOT_TRUST = "Do not trust with any data"
    RETIRE = "Retire immediately"


class GlobalConfidence(str, Enum):
    """How complete the evidence base is across all checks."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class ConflictNote:
    """Records a disagreement between two checks.

    Example: SMART says PASS but surface scan found read errors.
    """
    check_a: str
    verdict_a: str
    check_b: str
    verdict_b: str
    explanation: str


@dataclass
class GlobalVerdict:
    """The single, final assessment of a drive's health.

    Produced by ``compute_global_verdict()`` from a list of CheckResults.
    Consumed by the CLI formatter and JSON serializer.
    """
    health: OverallHealth
    urgency: Urgency
    usage: RecommendedUsage
    confidence: GlobalConfidence

    # All findings from all checks, merged and deduplicated.
    all_findings: List[Dict[str, Any]] = field(default_factory=list)

    # The subset of findings that most influenced the verdict.
    key_findings: List[Dict[str, Any]] = field(default_factory=list)

    # Cross-check conflicts detected.
    conflicts: List[ConflictNote] = field(default_factory=list)

    # Per-check verdicts that fed into this global result.
    check_verdicts: Dict[str, str] = field(default_factory=dict)

    # Human-readable explanation of why this verdict was chosen.
    reasoning: str = ""

    # Advisory composite score (0-100).
    composite_score: int = 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "health": self.health.value,
            "urgency": self.urgency.value,
            "recommended_usage": self.usage.value,
            "confidence": self.confidence.value,
            "composite_score": self.composite_score,
            "reasoning": self.reasoning,
            "check_verdicts": self.check_verdicts,
            "key_findings": self.key_findings,
            "conflicts": [
                {
                    "check_a": c.check_a,
                    "verdict_a": c.verdict_a,
                    "check_b": c.check_b,
                    "verdict_b": c.verdict_b,
                    "explanation": c.explanation,
                }
                for c in self.conflicts
            ],
            "all_findings_count": len(self.all_findings),
        }
