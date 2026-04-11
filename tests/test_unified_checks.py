"""Tests for migrated checks (filesystem, surface, stress, integrity).

Verifies each check now produces structured findings through the
unified pipeline and that the output is consistent.
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

import pytest

from disk_health_checker.models.config import (
    FsConfig,
    GlobalConfig,
    IntegrityConfig,
    StressConfig,
    SurfaceScanConfig,
)
from disk_health_checker.models.results import Severity


# ── Helpers ──────────────────────────────────────────────────────────


def _assert_unified_schema(cr):
    """Assert a CheckResult has the unified pipeline schema."""
    d = cr.details
    assert "verdict" in d, f"Missing 'verdict' in {cr.check_name}"
    assert "confidence" in d, f"Missing 'confidence' in {cr.check_name}"
    assert "health_score" in d, f"Missing 'health_score' in {cr.check_name}"
    assert "findings" in d, f"Missing 'findings' in {cr.check_name}"
    assert isinstance(d["findings"], list)
    assert "evidence_missing" in d, f"Missing 'evidence_missing' in {cr.check_name}"
    assert isinstance(d["evidence_missing"], list)
    # Verdict must be a valid string
    assert d["verdict"] in ("PASS", "WARNING", "FAIL", "UNKNOWN")
    assert d["confidence"] in ("HIGH", "MEDIUM", "LOW")
    assert isinstance(d["health_score"], int)
    assert 0 <= d["health_score"] <= 100
    # Each finding must have required fields
    for f in d["findings"]:
        assert "code" in f
        assert "severity" in f
        assert "message" in f
        assert "evidence" in f
        assert f["severity"] in ("INFO", "WARN", "FAIL")


# ── Filesystem ───────────────────────────────────────────────────────


class TestFilesystemUnified:
    def test_nonexistent_mount_produces_fail_finding(self):
        from disk_health_checker.checks.filesystem import run_filesystem_check
        cfg = FsConfig(mount_point="/nonexistent/path/12345")
        gc = GlobalConfig()
        cr = run_filesystem_check(cfg, gc)
        _assert_unified_schema(cr)
        assert cr.status == Severity.CRITICAL
        assert cr.details["verdict"] == "FAIL"
        codes = [f["code"] for f in cr.details["findings"]]
        assert "fs.mount_not_found" in codes

    def test_valid_mount_produces_pass(self):
        from disk_health_checker.checks.filesystem import run_filesystem_check
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = FsConfig(mount_point=tmpdir)
            gc = GlobalConfig(non_destructive=True)
            cr = run_filesystem_check(cfg, gc)
            _assert_unified_schema(cr)
            assert cr.status == Severity.OK
            assert cr.details["verdict"] == "PASS"
            assert cr.details["confidence"] == "HIGH"

    def test_write_failure_produces_fail_finding(self):
        from disk_health_checker.checks.filesystem import run_filesystem_check
        with tempfile.TemporaryDirectory() as tmpdir:
            # Make directory read-only to force write failure
            os.chmod(tmpdir, 0o444)
            try:
                cfg = FsConfig(mount_point=tmpdir)
                gc = GlobalConfig(non_destructive=True)
                cr = run_filesystem_check(cfg, gc)
                _assert_unified_schema(cr)
                assert cr.status == Severity.CRITICAL
                codes = [f["code"] for f in cr.details["findings"]]
                assert "fs.write_test_failed" in codes
            finally:
                os.chmod(tmpdir, 0o755)

    def test_non_destructive_disabled_skips_write_test(self):
        from disk_health_checker.checks.filesystem import run_filesystem_check
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = FsConfig(mount_point=tmpdir)
            gc = GlobalConfig(non_destructive=False)
            cr = run_filesystem_check(cfg, gc)
            _assert_unified_schema(cr)
            assert cr.status == Severity.OK

    def test_fsck_requested_produces_info_finding(self):
        from disk_health_checker.checks.filesystem import run_filesystem_check
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = FsConfig(mount_point=tmpdir, run_external_fsck=True)
            gc = GlobalConfig()
            cr = run_filesystem_check(cfg, gc)
            _assert_unified_schema(cr)
            codes = [f["code"] for f in cr.details["findings"]]
            assert "fs.fsck_skipped" in codes


# ── Surface Scan ─────────────────────────────────────────────────────


class TestSurfaceScanUnified:
    def test_nonexistent_device_produces_fail_finding(self):
        from disk_health_checker.checks.surface import run_surface_scan
        cfg = SurfaceScanConfig(device="/dev/nonexistent12345")
        gc = GlobalConfig(json_output=True)
        cr = run_surface_scan(cfg, gc)
        _assert_unified_schema(cr)
        assert cr.status == Severity.CRITICAL
        assert cr.details["verdict"] == "FAIL"
        codes = [f["code"] for f in cr.details["findings"]]
        assert "surface.device_not_found" in codes

    def test_readable_file_produces_pass(self):
        from disk_health_checker.checks.surface import run_surface_scan
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"\x00" * 4096 * 10)
            f.flush()
            path = f.name
        try:
            cfg = SurfaceScanConfig(device=path, quick=False, block_size=4096)
            gc = GlobalConfig(json_output=True)
            cr = run_surface_scan(cfg, gc)
            _assert_unified_schema(cr)
            assert cr.status == Severity.OK
            assert cr.details["verdict"] == "PASS"
            assert cr.details["blocks_read"] > 0
        finally:
            os.unlink(path)


# ── Stress Test ──────────────────────────────────────────────────────


class TestStressTestUnified:
    def test_nonexistent_target_produces_fail_finding(self):
        from disk_health_checker.checks.stress import run_stress_test
        cfg = StressConfig(mount_point="/nonexistent/path/12345")
        gc = GlobalConfig()
        cr = run_stress_test(cfg, gc)
        _assert_unified_schema(cr)
        assert cr.status == Severity.CRITICAL
        assert cr.details["verdict"] == "FAIL"
        codes = [f["code"] for f in cr.details["findings"]]
        assert "stress.target_not_found" in codes

    def test_short_stress_on_tmpdir_passes(self):
        from disk_health_checker.checks.stress import run_stress_test
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = StressConfig(
                mount_point=tmpdir,
                duration_seconds=1,
                threads=1,
                max_space_fraction=0.01,
            )
            gc = GlobalConfig()
            cr = run_stress_test(cfg, gc)
            _assert_unified_schema(cr)
            # Should pass unless the machine is critically out of space
            assert cr.details["verdict"] in ("PASS", "WARNING")
            assert cr.details["ops"] >= 0


# ── Integrity ────────────────────────────────────────────────────────


class TestIntegrityUnified:
    def test_nonexistent_target_produces_fail_finding(self):
        from disk_health_checker.checks.integrity import run_integrity_check
        cfg = IntegrityConfig(mount_point="/nonexistent/path/12345")
        gc = GlobalConfig()
        cr = run_integrity_check(cfg, gc)
        _assert_unified_schema(cr)
        assert cr.status == Severity.CRITICAL
        assert cr.details["verdict"] == "FAIL"
        codes = [f["code"] for f in cr.details["findings"]]
        assert "integrity.target_not_found" in codes

    def test_pattern_check_passes_on_tmpdir(self):
        from disk_health_checker.checks.integrity import run_integrity_check
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = IntegrityConfig(mount_point=tmpdir)
            gc = GlobalConfig()
            cr = run_integrity_check(cfg, gc)
            _assert_unified_schema(cr)
            assert cr.status == Severity.OK
            assert cr.details["verdict"] == "PASS"
            assert cr.details["pattern_mismatches"] == 0

    def test_manifest_mismatch_produces_warn_finding(self):
        import json
        from disk_health_checker.checks.integrity import run_integrity_check
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("hello world")

            # Create a manifest with wrong checksum
            manifest = {
                "algorithm": "sha256",
                "files": {"test.txt": "0000000000000000000000000000000000000000000000000000000000000000"},
            }
            manifest_path = os.path.join(tmpdir, "manifest.json")
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)

            cfg = IntegrityConfig(
                mount_point=tmpdir, manifest_path=manifest_path,
            )
            gc = GlobalConfig()
            cr = run_integrity_check(cfg, gc)
            _assert_unified_schema(cr)
            assert cr.details["verdict"] in ("WARNING", "FAIL")
            codes = [f["code"] for f in cr.details["findings"]]
            assert "integrity.manifest_mismatch" in codes

    def test_manifest_missing_file_produces_warn_finding(self):
        import json
        from disk_health_checker.checks.integrity import run_integrity_check
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = {
                "algorithm": "sha256",
                "files": {"does_not_exist.txt": "abc123"},
            }
            manifest_path = os.path.join(tmpdir, "manifest.json")
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)

            cfg = IntegrityConfig(
                mount_point=tmpdir, manifest_path=manifest_path,
            )
            gc = GlobalConfig()
            cr = run_integrity_check(cfg, gc)
            _assert_unified_schema(cr)
            codes = [f["code"] for f in cr.details["findings"]]
            assert "integrity.manifest_missing_files" in codes


# ── Cross-check: SMART also produces unified schema ──────────────────


class TestSmartUnifiedSchema:
    """Verify SMART CheckResults also conform to the unified schema."""

    def test_interpret_smart_has_unified_fields(self):
        """interpret_smart() should produce details with verdict/findings."""
        from disk_health_checker.checks.smart import interpret_smart

        # Minimal ATA-like smartctl JSON
        data = {
            "device": {"type": "ata"},
            "smart_status": {"passed": True},
            "ata_smart_attributes": {
                "table": [
                    {
                        "id": 5, "name": "Reallocated_Sector_Ct",
                        "value": 100, "raw": {"value": 0, "string": "0"},
                    },
                    {
                        "id": 197, "name": "Current_Pending_Sector",
                        "value": 100, "raw": {"value": 0, "string": "0"},
                    },
                    {
                        "id": 198, "name": "Offline_Uncorrectable",
                        "value": 100, "raw": {"value": 0, "string": "0"},
                    },
                ]
            },
        }

        cr = interpret_smart(data)
        _assert_unified_schema(cr)
        assert cr.details["verdict"] == "PASS"
        assert cr.check_name == "SMART"
        # SMART-specific extra details should also be present
        assert "model_name" in cr.details
        assert "device_kind" in cr.details


# ── Cross-check: all checks agree on severity mapping ────────────────


class TestSeverityConsistency:
    """PASS=OK, WARNING=WARNING, FAIL=CRITICAL, UNKNOWN=UNKNOWN everywhere."""

    def test_filesystem_pass_is_ok(self):
        from disk_health_checker.checks.filesystem import run_filesystem_check
        with tempfile.TemporaryDirectory() as tmpdir:
            cr = run_filesystem_check(FsConfig(mount_point=tmpdir), GlobalConfig())
            assert cr.details["verdict"] == "PASS"
            assert cr.status == Severity.OK

    def test_filesystem_fail_is_critical(self):
        from disk_health_checker.checks.filesystem import run_filesystem_check
        cr = run_filesystem_check(
            FsConfig(mount_point="/nonexistent/12345"), GlobalConfig(),
        )
        assert cr.details["verdict"] == "FAIL"
        assert cr.status == Severity.CRITICAL

    def test_surface_fail_is_critical(self):
        from disk_health_checker.checks.surface import run_surface_scan
        cr = run_surface_scan(
            SurfaceScanConfig(device="/dev/nonexistent12345"),
            GlobalConfig(json_output=True),
        )
        assert cr.details["verdict"] == "FAIL"
        assert cr.status == Severity.CRITICAL
