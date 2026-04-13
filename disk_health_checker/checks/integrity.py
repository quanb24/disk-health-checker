"""Data integrity verification.

Writes known patterns and reads them back to verify the storage medium
correctly stores and retrieves data.  Optionally verifies files against
a checksum manifest.

Produces structured findings fed through the unified verdict pipeline.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Tuple

from ..models.config import IntegrityConfig, GlobalConfig
from ..models.results import CheckResult
from ..models.smart_types import Confidence, Finding, FindingSeverity
from ..utils.validation import safe_path, validate_hash_algorithm
from .evaluate import findings_to_verdict, verdict_to_check_result

logger = logging.getLogger(__name__)


def _hash_file(path: str, algorithm: str, max_bytes: int) -> Tuple[str, int]:
    h = hashlib.new(algorithm)
    total = 0
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
            if total >= max_bytes:
                break
    return h.hexdigest(), total


def _temp_pattern_integrity_check(config: IntegrityConfig) -> Dict[str, Any]:
    """Write known patterns and verify readback correctness."""
    patterns = [b"\x00" * 4096, b"\xff" * 4096, os.urandom(4096)]
    mismatches = 0
    total_tests = 0

    with tempfile.TemporaryDirectory(
        dir=config.mount_point, prefix=".dhc-int-"
    ) as tmpdir:
        for idx, pattern in enumerate(patterns):
            total_tests += 1
            path = os.path.join(tmpdir, f"pattern-{idx}")
            try:
                with open(path, "wb") as f:
                    f.write(pattern)
                    f.flush()
                    os.fsync(f.fileno())
                with open(path, "rb") as f:
                    data = f.read()
                if data != pattern:
                    mismatches += 1
            except Exception as exc:
                logger.warning("Integrity temp pattern check failed: %s", exc)
                mismatches += 1

    return {"pattern_tests": total_tests, "pattern_mismatches": mismatches}


def _manifest_integrity_check(config: IntegrityConfig) -> Dict[str, Any]:
    """Verify files match a JSON checksum manifest."""
    if not config.manifest_path or not os.path.isfile(config.manifest_path):
        return {"manifest_error": "manifest file not provided or not found"}

    with open(config.manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    raw_algo = manifest.get("algorithm", config.algorithm)
    try:
        algo = validate_hash_algorithm(raw_algo)
    except ValueError:
        return {
            "manifest_error": f"Unsupported hash algorithm in manifest: {raw_algo!r}",
            "manifest_checked_files": [],
            "manifest_mismatched_files": [],
            "manifest_missing_files": [],
        }
    files: Dict[str, str] = manifest.get("files", {})

    mismatches: List[str] = []
    missing: List[str] = []
    checked: List[str] = []
    traversal_blocked: List[str] = []

    for rel_path, expected in files.items():
        try:
            full_path = safe_path(config.mount_point, rel_path)
        except ValueError:
            logger.warning("Path traversal blocked in manifest: %r", rel_path)
            traversal_blocked.append(rel_path)
            continue
        if not os.path.isfile(full_path):
            missing.append(rel_path)
            continue
        try:
            digest, _ = _hash_file(full_path, algo, config.max_file_size_bytes)
        except Exception as exc:
            logger.warning("Failed to hash %s: %s", full_path, exc)
            mismatches.append(rel_path)
            continue
        checked.append(rel_path)
        if digest != expected:
            mismatches.append(rel_path)

    return {
        "manifest_algorithm": algo,
        "manifest_checked_files": checked,
        "manifest_mismatched_files": mismatches,
        "manifest_missing_files": missing,
        "manifest_traversal_blocked": traversal_blocked,
    }


def run_integrity_check(
    config: IntegrityConfig, global_config: GlobalConfig,
) -> CheckResult:
    mount = config.mount_point
    findings: List[Finding] = []
    extra_details: Dict[str, Any] = {"mount_point": mount}

    # ── Target existence ──
    if not os.path.isdir(mount):
        findings.append(Finding(
            code="integrity.target_not_found",
            severity=FindingSeverity.FAIL,
            message=f"Integrity target is not a directory: {mount}",
            evidence={"mount_point": mount},
        ))
        vr = findings_to_verdict(
            findings, confidence=Confidence.HIGH, check_category="integrity",
        )
        return verdict_to_check_result(
            "Integrity", vr,
            extra_details=extra_details,
            target_description=mount,
        )

    # ── Pattern integrity ──
    pattern_results = _temp_pattern_integrity_check(config)
    extra_details.update(pattern_results)

    mismatches = pattern_results.get("pattern_mismatches", 0)
    if mismatches > 0:
        findings.append(Finding(
            code="integrity.pattern_mismatch",
            severity=FindingSeverity.FAIL,
            message=f"{mismatches} pattern mismatch(es) detected — data written does not match data read back.",
            evidence={
                "pattern_tests": pattern_results["pattern_tests"],
                "pattern_mismatches": mismatches,
            },
        ))

    # ── Manifest integrity ──
    if config.manifest_path:
        manifest_results = _manifest_integrity_check(config)
        extra_details.update(manifest_results)

        manifest_mismatches = manifest_results.get("manifest_mismatched_files", [])
        manifest_missing = manifest_results.get("manifest_missing_files", [])

        if manifest_mismatches:
            findings.append(Finding(
                code="integrity.manifest_mismatch",
                severity=FindingSeverity.WARN,
                message=f"{len(manifest_mismatches)} file(s) do not match their expected checksums.",
                evidence={"mismatched_files": manifest_mismatches},
            ))

        if manifest_missing:
            findings.append(Finding(
                code="integrity.manifest_missing_files",
                severity=FindingSeverity.WARN,
                message=f"{len(manifest_missing)} file(s) listed in manifest are missing.",
                evidence={"missing_files": manifest_missing},
            ))

        manifest_traversal = manifest_results.get("manifest_traversal_blocked", [])
        if manifest_traversal:
            findings.append(Finding(
                code="integrity.manifest_path_escape",
                severity=FindingSeverity.FAIL,
                message=f"{len(manifest_traversal)} manifest path(s) blocked: attempted directory traversal outside mount point.",
                evidence={"blocked_paths": manifest_traversal},
            ))

    confidence = Confidence.HIGH

    vr = findings_to_verdict(
        findings, confidence=confidence, check_category="integrity",
    )
    return verdict_to_check_result(
        "Integrity", vr,
        extra_details=extra_details,
        target_description=mount,
    )
