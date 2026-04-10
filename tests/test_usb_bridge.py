"""Tests for USB bridge fallback chain and UsbBridgeBlocked error handling.

All tests monkeypatch subprocess.run so no real smartctl is needed.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from disk_health_checker.checks.smart.collector import (
    collect_smart,
    USB_FALLBACK_CHAIN,
)
from disk_health_checker.checks.smart.errors import (
    UsbBridgeBlocked,
    SmartNotSupported,
    SmartctlProtocolError,
)


def _fake_which(cmd: str):
    if cmd == "smartctl":
        return "/usr/local/bin/smartctl"
    return None


def _make_completed(stdout_dict=None, stderr="", returncode=0):
    stdout = json.dumps(stdout_dict or {})
    return subprocess.CompletedProcess(
        args=["smartctl"], returncode=returncode, stdout=stdout, stderr=stderr,
    )


# ---- USB fallback chain triggers on known phrases ----

class TestUsbFallbackTrigger:
    """Fallback chain activates when stderr contains USB bridge hints."""

    def test_triggers_on_unknown_usb_bridge(self, monkeypatch):
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        calls = []

        def record_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                return _make_completed(
                    returncode=1,
                    stderr="Unknown USB bridge [0x1234:0x5678]",
                )
            return _make_completed(stdout_dict={"ok": True}, returncode=0)

        monkeypatch.setattr("subprocess.run", record_run)
        result = collect_smart("/dev/disk4")
        assert result.retried_with_sat is True
        assert result.data == {"ok": True}

    def test_triggers_on_specify_device_type(self, monkeypatch):
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        calls = []

        def record_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                return _make_completed(
                    returncode=1,
                    stderr="Please specify device type with -d option.",
                )
            return _make_completed(stdout_dict={"ok": True}, returncode=0)

        monkeypatch.setattr("subprocess.run", record_run)
        result = collect_smart("/dev/disk4")
        assert result.retried_with_sat is True

    def test_triggers_on_unable_to_detect(self, monkeypatch):
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        calls = []

        def record_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                return _make_completed(
                    returncode=1,
                    stderr="Unable to detect device type",
                )
            return _make_completed(stdout_dict={"ok": True}, returncode=0)

        monkeypatch.setattr("subprocess.run", record_run)
        result = collect_smart("/dev/disk4")
        assert result.retried_with_sat is True


# ---- USB transport hint triggers fallback even without keyword ----

class TestUsbTransportHint:
    """When transport='USB', fallback chain runs even for non-keyword errors."""

    def test_usb_transport_triggers_fallback(self, monkeypatch):
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        calls = []

        def record_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                return _make_completed(
                    returncode=1,
                    stderr="Smartctl open device: /dev/disk4 failed: Operation not supported by device",
                )
            return _make_completed(stdout_dict={"ok": True}, returncode=0)

        monkeypatch.setattr("subprocess.run", record_run)
        result = collect_smart("/dev/disk4", transport="USB")
        assert result.retried_with_sat is True
        assert len(calls) == 2

    def test_non_usb_transport_skips_fallback(self, monkeypatch):
        """Non-USB drives don't trigger the fallback chain on generic errors."""
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **kw: _make_completed(
                returncode=4, stderr="some unknown error"
            ),
        )
        with pytest.raises(SmartctlProtocolError):
            collect_smart("/dev/disk0", transport="NVMe")


# ---- Fallback chain stops early on "not a device of type" ----

class TestEarlyStopOnNotScsi:
    """Chain stops when OS says device isn't SCSI-compatible."""

    def test_stops_on_not_a_device_of_type(self, monkeypatch):
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        calls = []

        def record_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                return _make_completed(
                    returncode=1,
                    stderr="Unknown USB bridge",
                )
            # All retries get "not a device of type 'scsi'"
            return _make_completed(
                returncode=1,
                stderr="/dev/disk4: Type 'sat+...': Not a device of type 'scsi'",
            )

        monkeypatch.setattr("subprocess.run", record_run)
        with pytest.raises(UsbBridgeBlocked) as exc_info:
            collect_smart("/dev/disk4")
        # Should have stopped after first retry hit "not a device of type"
        assert len(calls) == 2
        assert "auto" in exc_info.value.types_tried

    def test_stops_on_operation_not_supported(self, monkeypatch):
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        calls = []

        def record_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                return _make_completed(returncode=1, stderr="Unknown USB bridge")
            return _make_completed(
                returncode=1,
                stderr="Operation not supported by device",
            )

        monkeypatch.setattr("subprocess.run", record_run)
        with pytest.raises(UsbBridgeBlocked):
            collect_smart("/dev/disk4")
        assert len(calls) == 2


# ---- Full chain exhaustion raises UsbBridgeBlocked ----

class TestUsbBridgeBlocked:
    """When all fallback modes fail, UsbBridgeBlocked is raised."""

    def test_all_modes_fail_raises_usb_bridge_blocked(self, monkeypatch):
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        calls = []

        def record_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) == 1:
                return _make_completed(returncode=1, stderr="Unknown USB bridge")
            # All retries fail with a non-SCSI-blocking error
            return _make_completed(returncode=1, stderr="some other failure")

        monkeypatch.setattr("subprocess.run", record_run)
        with pytest.raises(UsbBridgeBlocked) as exc_info:
            collect_smart("/dev/disk4")
        # auto + all fallback chain entries
        expected_count = 1 + len(USB_FALLBACK_CHAIN)
        assert len(calls) == expected_count
        assert exc_info.value.device == "/dev/disk4"
        assert len(exc_info.value.types_tried) == expected_count

    def test_usb_blocked_error_message_is_helpful(self):
        exc = UsbBridgeBlocked("/dev/disk4", types_tried=["auto", "sat", "sat,12"])
        msg = str(exc)
        assert "USB enclosure" in msg
        assert "hardware limitation" in msg
        assert "SATA" in msg
        assert "auto, sat, sat,12" in msg


# ---- Successful fallback records device_type_used ----

class TestSuccessfulFallback:
    """When a fallback mode succeeds, it's recorded in the result."""

    def test_records_successful_device_type(self, monkeypatch):
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        calls = []

        def record_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) <= 2:
                # auto and first fallback fail
                return _make_completed(returncode=1, stderr="Unknown USB bridge")
            # Second fallback succeeds
            return _make_completed(stdout_dict={"ok": True}, returncode=0)

        monkeypatch.setattr("subprocess.run", record_run)
        result = collect_smart("/dev/disk4")
        assert result.device_type_used == "sat,12"
        assert result.retried_with_sat is True
        assert any("sat,12" in w for w in result.warnings)

    def test_device_types_tried_is_populated(self, monkeypatch):
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        calls = []

        def record_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) <= 3:
                return _make_completed(returncode=1, stderr="Unknown USB bridge")
            return _make_completed(stdout_dict={"ok": True}, returncode=0)

        monkeypatch.setattr("subprocess.run", record_run)
        result = collect_smart("/dev/disk4")
        assert "auto" in result.device_types_tried
        assert "sat" in result.device_types_tried
        assert "sat,12" in result.device_types_tried


# ---- Internal drives unaffected ----

class TestInternalDriveUnaffected:
    """Normal SATA/NVMe drives skip the fallback chain entirely."""

    def test_successful_first_attempt_no_retry(self, monkeypatch):
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        calls = []

        def record_run(cmd, **kwargs):
            calls.append(cmd)
            return _make_completed(
                stdout_dict={"smart_status": {"passed": True}},
                returncode=0,
            )

        monkeypatch.setattr("subprocess.run", record_run)
        result = collect_smart("/dev/disk0")
        assert len(calls) == 1
        assert result.retried_with_sat is False
        assert result.device_type_used is None
        assert result.device_types_tried == ["auto"]

    def test_nvme_transport_no_fallback_on_success(self, monkeypatch):
        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)
        calls = []

        def record_run(cmd, **kwargs):
            calls.append(cmd)
            return _make_completed(
                stdout_dict={"nvme_smart_health_information_log": {}},
                returncode=0,
            )

        monkeypatch.setattr("subprocess.run", record_run)
        result = collect_smart("/dev/disk0", transport="NVMe")
        assert len(calls) == 1
        assert result.retried_with_sat is False


# ---- run_smart_check integration with UsbBridgeBlocked ----

class TestRunSmartCheckUsbBlocked:
    """run_smart_check returns a useful CheckResult for USB blocked drives."""

    def test_usb_blocked_returns_informative_check_result(self, monkeypatch):
        from disk_health_checker.checks.smart import run_smart_check
        from disk_health_checker.models.config import SmartConfig
        from disk_health_checker.models.results import Severity

        monkeypatch.setattr("disk_health_checker.checks.smart.collector.which", _fake_which)

        def fail_all(cmd, **kwargs):
            return _make_completed(returncode=1, stderr="Unknown USB bridge")

        monkeypatch.setattr("subprocess.run", fail_all)

        cfg = SmartConfig(device="/dev/disk4")
        result = run_smart_check(cfg, transport="USB")

        assert result.status == Severity.UNKNOWN
        assert result.details["failure_reason"] == "usb_bridge_blocked"
        assert "USB enclosure" in result.summary
        assert any("SATA" in r for r in result.recommendations)
        assert any("hardware limitation" in r for r in result.recommendations)
