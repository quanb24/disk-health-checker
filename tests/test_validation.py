"""Tests for input validation utilities (SEC-01, SEC-02, SEC-03)."""
from __future__ import annotations

import os
import tempfile

import pytest

from disk_health_checker.utils.validation import (
    validate_device_path,
    safe_path,
    validate_hash_algorithm,
    ALLOWED_HASH_ALGORITHMS,
)


class TestValidateDevicePath:
    """SEC-01: Device path argument injection prevention."""

    @pytest.mark.parametrize("path", [
        "/dev/disk0",
        "/dev/disk4",
        "/dev/rdisk2",
        "/dev/sda",
        "/dev/sdb1",
        "/dev/vda",
        "/dev/nvme0n1",
        "/dev/nvme0n1p1",
        "/dev/nvme1n2p3",
        "/dev/mmcblk0",
        "/dev/mmcblk0p1",
        "/dev/xvda",
        "/dev/loop0",
        "/dev/dm-0",
        "/dev/md0",
    ])
    def test_valid_paths_accepted(self, path):
        assert validate_device_path(path) == path

    @pytest.mark.parametrize("path", [
        "",
        "/dev/null",
        "/dev/../etc/passwd",
        "/dev/sda; rm -rf /",
        "/dev/sda && echo pwned",
        "../../etc/shadow",
        "/tmp/fake",
        "--scan",
        "-d sat",
        "/dev/",
        "/dev/ sda",
        "/dev/sda\nmalicious",
    ])
    def test_invalid_paths_rejected(self, path):
        with pytest.raises(ValueError, match="Invalid device path"):
            validate_device_path(path)


class TestSafePath:
    """SEC-02: Path traversal prevention for manifest files."""

    def test_normal_relative_path(self, tmp_path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").touch()
        result = safe_path(str(tmp_path), "subdir/file.txt")
        assert result == str(subdir / "file.txt")

    def test_traversal_blocked(self, tmp_path):
        with pytest.raises(ValueError, match="Path traversal blocked"):
            safe_path(str(tmp_path), "../../etc/passwd")

    def test_absolute_path_blocked(self, tmp_path):
        with pytest.raises(ValueError, match="Path traversal blocked"):
            safe_path(str(tmp_path), "/etc/passwd")

    def test_base_itself_allowed(self, tmp_path):
        result = safe_path(str(tmp_path), ".")
        assert result == str(tmp_path.resolve())

    def test_symlink_outside_blocked(self, tmp_path):
        target = tempfile.mkdtemp()
        link = tmp_path / "escape"
        os.symlink(target, link)
        with pytest.raises(ValueError, match="Path traversal blocked"):
            safe_path(str(tmp_path), "escape/../../../etc/passwd")


class TestValidateHashAlgorithm:
    """SEC-03: Hash algorithm allowlist."""

    @pytest.mark.parametrize("algo", sorted(ALLOWED_HASH_ALGORITHMS))
    def test_allowed_algorithms_accepted(self, algo):
        assert validate_hash_algorithm(algo) == algo

    @pytest.mark.parametrize("algo", [
        "md5",
        "sha1",
        "shake_256",
        "md4",
        "",
        "scrypt",
    ])
    def test_disallowed_algorithms_rejected(self, algo):
        with pytest.raises(ValueError, match="Unsupported hash algorithm"):
            validate_hash_algorithm(algo)
