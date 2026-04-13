"""Tests for CLI argument parsing, device resolution, and exit codes."""
from __future__ import annotations

import pytest

from disk_health_checker.cli import main, EXIT_OPERATIONAL_ERROR


class _FakeLinux:
    is_macos = False
    is_linux = True
    os_name = "Linux"
    arch = "x86_64"


class _FakeMacOS:
    is_macos = True
    is_linux = False
    os_name = "Darwin"
    arch = "arm64"


def _patch_platform(monkeypatch, fake):
    """Patch get_platform_info everywhere it's imported."""
    factory = lambda: fake
    monkeypatch.setattr("disk_health_checker.cli.get_platform_info", factory)
    monkeypatch.setattr("disk_health_checker.utils.disks.get_platform_info", factory)


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_no_command_exits_error():
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0


def test_smart_no_device_no_macos_exits_operational_error(monkeypatch):
    """On non-macOS without --device, should exit with operational error."""
    _patch_platform(monkeypatch, _FakeLinux())
    result = main(["smart"])
    assert result == EXIT_OPERATIONAL_ERROR


def test_json_mode_without_device_exits_operational_error(monkeypatch, capsys):
    """--json without --device must fail, not prompt interactively."""
    _patch_platform(monkeypatch, _FakeMacOS())
    result = main(["--json", "smart"])
    assert result == EXIT_OPERATIONAL_ERROR
    captured = capsys.readouterr()
    assert "required" in captured.err.lower()


def test_smart_with_nonexistent_device_returns_unknown(monkeypatch):
    """smartctl not installed -> UNKNOWN exit code 3."""
    _patch_platform(monkeypatch, _FakeLinux())
    monkeypatch.setattr(
        "disk_health_checker.checks.smart.collector.which",
        lambda _: None,
    )
    result = main(["smart", "--device", "/dev/sda"])
    assert result == 3


def test_doctor_without_device_no_macos_exits_operational_error(monkeypatch):
    _patch_platform(monkeypatch, _FakeLinux())
    result = main(["doctor"])
    assert result == EXIT_OPERATIONAL_ERROR


def test_full_without_device_no_macos_exits_operational_error(monkeypatch):
    _patch_platform(monkeypatch, _FakeLinux())
    result = main(["full"])
    assert result == EXIT_OPERATIONAL_ERROR
