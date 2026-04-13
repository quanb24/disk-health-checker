from __future__ import annotations

from dataclasses import dataclass, asdict, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..verdict.types import GlobalVerdict


class Severity(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class CheckDetails(Dict[str, Any]):
    """Typed documentation of the expected keys in CheckResult.details.

    All checks produce these keys via the unified verdict pipeline
    (evaluate.verdict_to_check_result).  SMART checks add extra keys
    (model_name, serial_number, etc.) and error paths add failure_reason.

    Core keys (always present after verdict pipeline):
        verdict: str          — "PASS", "WARN", "FAIL", "UNKNOWN"
        confidence: str       — "HIGH", "MEDIUM", "LOW"
        health_score: int     — 0-100 composite score
        findings: list[dict]  — structured finding dicts
        evidence_missing: list[str] — data gaps

    Optional keys:
        failure_reason: str   — set on error paths
        internal_error: str   — exception type name (ARCH-04)
        model_name: str       — SMART identity
        serial_number: str    — SMART identity
        device_kind: str      — "ata" or "nvme"
        mount_point: str      — for fs/stress/integrity checks
    """


@dataclass
class CheckResult:
    check_name: str
    status: Severity
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


@dataclass
class SuiteResult:
    target: str
    overall_status: Severity
    check_results: List[CheckResult]
    started_at: datetime
    finished_at: datetime
    global_verdict: Optional[GlobalVerdict] = field(default=None)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "target": self.target,
            "overall_status": self.overall_status.value,
            "check_results": [c.to_dict() for c in self.check_results],
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }
        if self.global_verdict is not None:
            d["global_verdict"] = self.global_verdict.to_dict()
        return d
