"""Filesystem health check.

Verifies a mounted filesystem is accessible and writable.
Produces structured findings fed through the unified verdict pipeline.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import tempfile
from typing import Any, Dict, List

from ..models.config import FsConfig, GlobalConfig
from ..models.results import CheckResult
from ..models.smart_types import Confidence, Finding, FindingSeverity
from ..utils.platform import get_platform_info, which
from .evaluate import findings_to_verdict, verdict_to_check_result

logger = logging.getLogger(__name__)


def _get_fs_type(path: str) -> str:
    info = get_platform_info()
    if info.is_linux:
        try:
            with open("/proc/mounts", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] == path:
                        return parts[2]
        except OSError:
            pass
    try:
        os.statvfs(path)
        return "unknown"
    except OSError:
        return "unknown"


def _run_fsck_if_requested(path: str, run_external_fsck: bool) -> Dict[str, Any]:
    details: Dict[str, Any] = {}
    if not run_external_fsck:
        return details

    info = get_platform_info()
    if not info.is_linux:
        details["fsck"] = "external fsck not supported on this platform by this tool"
        return details

    fsck = which("fsck")
    if not fsck:
        details["fsck"] = "fsck not found on PATH"
        return details

    details["fsck"] = "fsck invocation skipped (device mapping from mount point not implemented)"
    return details


def run_filesystem_check(config: FsConfig, global_config: GlobalConfig) -> CheckResult:
    mount = config.mount_point
    findings: List[Finding] = []
    evidence_missing: List[str] = []
    extra_details: Dict[str, Any] = {"mount_point": mount}

    # ── Mount point existence ──
    if not os.path.exists(mount):
        findings.append(Finding(
            code="fs.mount_not_found",
            severity=FindingSeverity.FAIL,
            message=f"Mount point does not exist: {mount}",
            evidence={"mount_point": mount},
        ))
        vr = findings_to_verdict(
            findings,
            evidence_missing=evidence_missing,
            confidence=Confidence.HIGH,
            check_category="filesystem",
        )
        return verdict_to_check_result(
            "Filesystem", vr,
            extra_details=extra_details,
            target_description=mount,
        )

    # ── Filesystem type ──
    fs_type = _get_fs_type(mount)
    extra_details["filesystem_type"] = fs_type

    # ── Disk usage ──
    try:
        usage = shutil.disk_usage(mount)
        extra_details["total_bytes"] = usage.total
        extra_details["used_bytes"] = usage.used
        extra_details["free_bytes"] = usage.free
    except OSError as exc:
        logger.warning("Failed to get disk usage for %s: %s", mount, exc)

    # ── Write sanity check ──
    if global_config.non_destructive:
        try:
            with tempfile.NamedTemporaryFile(
                dir=mount, prefix=".dhc-fs-test-", delete=True
            ) as tmp:
                tmp.write(b"disk-health-checker fs test\n")
                tmp.flush()
                os.fsync(tmp.fileno())
        except Exception as exc:
            findings.append(Finding(
                code="fs.write_test_failed",
                severity=FindingSeverity.FAIL,
                message=f"Failed to create a small test file under {mount}.",
                evidence={"error": str(exc), "mount_point": mount},
            ))
    else:
        extra_details["sanity_check"] = (
            "skipped because non-destructive safeguards are disabled"
        )

    # ── External fsck ──
    fsck_details = _run_fsck_if_requested(mount, config.run_external_fsck)
    if fsck_details.get("fsck"):
        findings.append(Finding(
            code="fs.fsck_skipped",
            severity=FindingSeverity.INFO,
            message=fsck_details["fsck"],
            evidence=fsck_details,
        ))
    extra_details.update(fsck_details)

    # ── Permissions ──
    try:
        st = os.stat(mount)
        extra_details["mode"] = oct(stat.S_IMODE(st.st_mode))
    except OSError:
        pass

    # ── Confidence ──
    # We could actually run the check, so confidence is HIGH.
    confidence = Confidence.HIGH

    vr = findings_to_verdict(
        findings,
        evidence_missing=evidence_missing,
        confidence=confidence,
        check_category="filesystem",
    )
    return verdict_to_check_result(
        "Filesystem", vr,
        extra_details=extra_details,
        target_description=mount,
    )
