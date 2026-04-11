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
