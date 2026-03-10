from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from typing import Dict, Any, List, Tuple

from ..models.config import IntegrityConfig, GlobalConfig
from ..models.results import CheckResult, Severity

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
    """
    Write a small temporary file with known content and verify it can be read back correctly.
    """
    patterns = [b"\x00" * 4096, b"\xff" * 4096, os.urandom(4096)]
    mismatches = 0
    total_tests = 0

    with tempfile.TemporaryDirectory(dir=config.mount_point, prefix=".dhc-int-") as tmpdir:
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
    """
    Verify existing files match a given manifest of checksums.
    Manifest format (JSON):
    {
      "algorithm": "sha256",
      "files": {
        "relative/path": "hex-digest",
        ...
      }
    }
    """
    if not config.manifest_path or not os.path.isfile(config.manifest_path):
        return {"manifest_error": "manifest file not provided or not found"}

    with open(config.manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    algo = manifest.get("algorithm", config.algorithm)
    files: Dict[str, str] = manifest.get("files", {})

    mismatches: List[str] = []
    missing: List[str] = []
    checked: List[str] = []

    for rel_path, expected in files.items():
        full_path = os.path.join(config.mount_point, rel_path)
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
    }


def run_integrity_check(config: IntegrityConfig, global_config: GlobalConfig) -> CheckResult:
    mount = config.mount_point

    if not os.path.isdir(mount):
        return CheckResult(
            check_name="Integrity",
            status=Severity.CRITICAL,
            summary=f"Integrity target is not a directory: {mount}",
            details={},
            recommendations=["Provide a valid mount point or directory for integrity checks."],
        )

    details: Dict[str, Any] = {}

    # Always run temp pattern checks
    details.update(_temp_pattern_integrity_check(config))

    # Optionally run manifest-based checks
    if config.manifest_path:
        details.update(_manifest_integrity_check(config))

    mismatches = details.get("pattern_mismatches", 0)
    manifest_mismatch_count = len(details.get("manifest_mismatched_files", []))
    manifest_missing_count = len(details.get("manifest_missing_files", []))

    status = Severity.OK
    recommendations = []
    summary_parts = ["Temporary pattern integrity checks completed."]

    if mismatches > 0:
        status = Severity.CRITICAL
        summary_parts.append(f"{mismatches} pattern mismatches detected.")
        recommendations.append("Investigate possible hardware issues; consider replacing the drive.")

    if manifest_mismatch_count > 0 or manifest_missing_count > 0:
        if status != Severity.CRITICAL:
            status = Severity.WARNING
        summary_parts.append(
            f"Manifest integrity issues: {manifest_mismatch_count} mismatches, {manifest_missing_count} missing files."
        )
        recommendations.append(
            "Re-verify data source and restore affected files from a known-good backup."
        )

    if status == Severity.OK:
        summary_parts.append("No integrity issues detected.")

    return CheckResult(
        check_name="Integrity",
        status=status,
        summary=" ".join(summary_parts),
        details=details,
        recommendations=recommendations,
    )


