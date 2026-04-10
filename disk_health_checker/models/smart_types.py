"""
Device-agnostic normalized SMART types.

These dataclasses decouple collection (smartctl invocation) from parsing
(raw JSON -> SmartSnapshot) and evaluation (SmartSnapshot -> Verdict).

Design rules:
- Every field that represents a measurement is Optional. Missing data is
  never silently conflated with zero.
- Parsers must record provenance notes in `parser_notes` when a value is
  decoded from a packed raw field or inferred, so the UI can say so.
- Evaluators must skip rules whose inputs are None and record the missing
  field name in `Verdict.evidence_missing` instead of guessing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


class DriveKind(str, Enum):
    ATA = "ata"          # includes SATA via smartctl -d sat
    NVME = "nvme"
    SCSI = "scsi"
    UNKNOWN = "unknown"


class Verdict(str, Enum):
    """User-facing health label. Distinct from Severity (machine-level)."""
    PASS = "PASS"
    WARNING = "WARNING"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Confidence(str, Enum):
    """How much of the minimum evidence floor the evaluator could read."""
    HIGH = "HIGH"      # full minimum signal set present
    MEDIUM = "MEDIUM"  # partial signal set; verdict is defensible but narrower
    LOW = "LOW"        # below the minimum evidence floor


class FindingSeverity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class Finding:
    """A single observation about the drive.

    `code` is a machine-stable identifier (e.g. "ata.reallocated.low",
    "nvme.critical_warning.reliability"). Scripts should match on `code`,
    not on the human `message`.
    """
    code: str
    severity: FindingSeverity
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SmartSnapshot:
    """Normalized, device-agnostic view of a drive's SMART state.

    Populated by parsing/{ata,nvme}.py from raw smartctl -j output.
    Consumed by evaluation/{ata,nvme}.py.
    """
    # ---- identity ----
    device_kind: DriveKind = DriveKind.UNKNOWN
    model: Optional[str] = None
    serial: Optional[str] = None
    firmware: Optional[str] = None
    capacity_bytes: Optional[int] = None
    rotation_rate_rpm: Optional[int] = None  # 0 -> SSD per ATA spec
    is_ssd: Optional[bool] = None

    # ---- overall ----
    overall_passed: Optional[bool] = None  # smartctl smart_status.passed
    power_on_hours: Optional[int] = None
    temperature_c: Optional[int] = None
    temperature_warning_c: Optional[int] = None   # drive-reported (NVMe)
    temperature_critical_c: Optional[int] = None  # drive-reported (NVMe)

    # ---- ATA-specific counters ----
    reallocated_sectors: Optional[int] = None
    pending_sectors: Optional[int] = None
    offline_uncorrectable: Optional[int] = None
    reported_uncorrect: Optional[int] = None
    udma_crc_errors: Optional[int] = None
    command_timeouts: Optional[int] = None

    # ---- wear (both families; sourced differently) ----
    # 0 = new, 100 = end-of-life design rating. NVMe native (percentage_used);
    # ATA derived from normalized value of the right attribute. None if we
    # could not confidently determine it.
    percent_life_used: Optional[int] = None
    available_spare_percent: Optional[int] = None      # NVMe
    available_spare_threshold: Optional[int] = None    # NVMe

    # ---- NVMe-only counters ----
    critical_warning_bits: Optional[int] = None
    media_errors: Optional[int] = None
    num_err_log_entries: Optional[int] = None
    unsafe_shutdowns: Optional[int] = None
    data_units_written: Optional[int] = None
    data_units_read: Optional[int] = None

    # ---- capability / provenance ----
    supports_self_test: Optional[bool] = None
    raw_source: Literal["smartctl-json"] = "smartctl-json"
    smartctl_version: Optional[str] = None
    parser_notes: List[str] = field(default_factory=list)
    unknown_fields: List[str] = field(default_factory=list)


@dataclass
class VerdictResult:
    """Result of evaluating a SmartSnapshot.

    Wraps a Verdict with the findings that produced it, a confidence level,
    an advisory 0-100 score, and an explicit list of signals the evaluator
    wanted but could not read. The verdict is determined by the worst
    finding, NOT by the score; score is advisory only.
    """
    verdict: Verdict
    confidence: Confidence
    score: int                            # 0-100, advisory
    findings: List[Finding] = field(default_factory=list)
    evidence_missing: List[str] = field(default_factory=list)
    reasoning: str = ""
