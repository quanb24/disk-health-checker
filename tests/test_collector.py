"""Tests for the smartctl collection layer.

All tests monkeypatch subprocess.run so no real smartctl is needed.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from disk_health_checker.checks.smart.collector import collect_smart
from disk_health_checker.checks.smart.errors import (
    SmartctlNotInstalled,
    SmartctlTimeout,
    SmartNotSupported,
    SmartctlProtocolError,
)


def _fake_which(cmd: str):
    """Pretend smartctl exists at /usr/local/bin/smartctl."""
    if cmd == "smartctl":
        return "/usr/local/bin/smartctl"
    return None


def _make_completed(stdout_dict=None, stderr="", returncode=0):
    stdout = json.dumps(stdout_dict or {})
    return subprocess.CompletedProcess(
        args=["smartctl"], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ---- SmartctlNotInstalled ----

def test_raises_not_installed_when_smartctl_missing(monkeypatch):
    monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", lambda _: None)
    with pytest.raises(SmartctlNotInstalled):
        collect_smart("/dev/disk99")


# ---- SmartctlTimeout ----

def test_raises_timeout(monkeypatch):
    monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="smartctl", timeout=30)
    monkeypatch.setattr("subprocess.run", timeout_run)
    with pytest.raises(SmartctlTimeout) as exc_info:
        collect_smart("/dev/disk99", timeout_s=30)
    assert exc_info.value.timeout_s == 30


# ---- SmartNotSupported ----

def test_raises_not_supported_on_enclosure_error(monkeypatch):
    monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: _make_completed(
            returncode=1,
            stderr="SMART support is: Unavailable - device lacks SMART capability.",
        ),
    )
    with pytest.raises(SmartNotSupported):
        collect_smart("/dev/disk99")


# ---- USB bridge retry ----

def test_retries_with_d_sat_on_usb_bridge(monkeypatch):
    monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
    calls = []
    def record_run(cmd, **kwargs):
        calls.append(cmd)
        if "-d" not in cmd:
            # First call fails with USB bridge message.
            return _make_completed(
                returncode=1,
                stderr="Unknown USB bridge [0x1234:0x5678]\nPlease specify device type with -d",
            )
        # Retry succeeds.
        return _make_completed(
            stdout_dict={"smart_status": {"passed": True}},
            returncode=0,
        )
    monkeypatch.setattr("subprocess.run", record_run)
    result = collect_smart("/dev/disk99")
    assert result.retried_with_sat is True
    assert result.data == {"smart_status": {"passed": True}}
    assert len(calls) == 2
    assert "-d" in calls[1]


# ---- Successful collection ----

def test_successful_collection_returns_data(monkeypatch):
    monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
    data = {
        "smartctl": {"version": [7, 4]},
        "smart_status": {"passed": True},
        "ata_smart_attributes": {"table": []},
    }
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: _make_completed(stdout_dict=data),
    )
    result = collect_smart("/dev/disk2")
    assert result.data["smart_status"]["passed"] is True
    assert result.smartctl_version == "7.4"
    assert result.retried_with_sat is False
    assert result.exit_code == 0
    assert result.warnings == []


# ---- Non-fatal exit code 2 ----

def test_exit_code_2_returns_with_warning(monkeypatch):
    monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
    data = {"smart_status": {"passed": True}}
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: _make_completed(stdout_dict=data, returncode=2),
    )
    result = collect_smart("/dev/disk2")
    assert result.data["smart_status"]["passed"] is True
    assert result.exit_code == 2
    assert len(result.warnings) == 1


# ---- Unclassified error ----

def test_unclassified_error_raises_protocol_error(monkeypatch):
    monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: _make_completed(returncode=4, stderr="some unknown problem"),
    )
    with pytest.raises(SmartctlProtocolError) as exc_info:
        collect_smart("/dev/disk2")
    assert exc_info.value.returncode == 4


# ---- JSON parse failure ----

def test_bad_json_raises_protocol_error(monkeypatch):
    monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **kw: subprocess.CompletedProcess(
            args=["smartctl"], returncode=0, stdout="NOT JSON", stderr="",
        ),
    )
    with pytest.raises(SmartctlProtocolError, match="Failed to parse JSON"):
        collect_smart("/dev/disk2")
