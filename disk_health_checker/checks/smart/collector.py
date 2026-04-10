"""Invoke smartctl and return raw parsed JSON.

This module does I/O only. It does not interpret SMART data.
All interpretation happens in the parsing and evaluation layers.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from disk_health_checker.utils.platform import which, get_platform_info
from .errors import (
    SmartctlNotInstalled,
    SmartctlTimeout,
    SmartNotSupported,
    SmartctlProtocolError,
    UsbBridgeBlocked,
)

logger = logging.getLogger(__name__)

# Seconds before we give up on smartctl.  A dying drive or stalled USB
# bridge can cause smartctl to block for a very long time.
DEFAULT_TIMEOUT_S = 30

# Device-type flags to try for USB-SATA bridges, in order.
# -d sat        — standard SAT (SCSI-to-ATA Translation), works on most docks
# -d sat,12     — 12-byte SAT CDB variant, needed by some older bridges
# -d sat,16     — 16-byte SAT CDB variant, needed by some WD/Seagate bridges
# -d usbsunplus — Sunplus-based USB bridge chips
# -d usbjmicron — JMicron-based USB bridge chips (very common in enclosures)
USB_FALLBACK_CHAIN: List[List[str]] = [
    ["-d", "sat"],
    ["-d", "sat,12"],
    ["-d", "sat,16"],
    ["-d", "usbsunplus"],
    ["-d", "usbjmicron"],
]

# Phrases in stderr that indicate the device type wasn't auto-detected
# and a retry with explicit -d flag may help.
_RETRY_TRIGGER_PHRASES = [
    "unknown usb bridge",
    "please specify device type with -d",
    "unable to detect device type",
]

# Phrases that mean the device is fundamentally unreachable via SCSI/SAT —
# no point trying further USB bridge types.
_DEVICE_NOT_SCSI_PHRASES = [
    "not a device of type",
    "operation not supported by device",
    "no such device",
    "permission denied",
]


@dataclass
class CollectionResult:
    """Raw smartctl output with metadata about how it was obtained."""
    data: Dict[str, Any]
    device: str
    retried_with_sat: bool = False
    device_type_used: Optional[str] = None
    device_types_tried: List[str] = field(default_factory=list)
    smartctl_version: Optional[str] = None
    exit_code: int = 0
    stderr: str = ""
    warnings: list[str] = field(default_factory=list)


def collect_smart(
    device: str,
    *,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    transport: Optional[str] = None,
) -> CollectionResult:
    """Run smartctl and return parsed JSON.

    Uses -H -A -i -j for a concise JSON report.  For USB-connected drives,
    tries a chain of SAT/bridge device types before giving up.

    Args:
        device: Block device path (e.g. /dev/disk4).
        timeout_s: Seconds before giving up on smartctl.
        transport: Bus protocol hint from disk enumeration (e.g. "USB",
            "SATA", "NVMe"). When "USB", the full fallback chain is tried.

    Raises:
        SmartctlNotInstalled: smartctl not on PATH.
        SmartctlTimeout: subprocess timed out.
        UsbBridgeBlocked: USB enclosure blocks all SMART passthrough.
        SmartNotSupported: device/enclosure does not expose SMART.
        SmartctlProtocolError: unclassified non-zero exit.
    """
    smartctl_path = which("smartctl")
    if not smartctl_path:
        raise SmartctlNotInstalled()

    is_usb = (transport or "").upper() == "USB"

    def invoke(extra_args: list[str]) -> subprocess.CompletedProcess[str]:
        cmd = [smartctl_path, "-H", "-A", "-i", "-j"] + extra_args + [device]
        try:
            return subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            raise SmartctlTimeout(device, timeout_s)
        except OSError as exc:
            raise SmartctlProtocolError(device, -1, str(exc))

    proc = invoke([])
    types_tried = ["auto"]
    device_type_used = None
    stderr_lower = (proc.stderr or "").lower()

    # If first attempt failed, try USB bridge fallback chain.
    if proc.returncode != 0:
        needs_fallback = any(
            phrase in stderr_lower for phrase in _RETRY_TRIGGER_PHRASES
        )
        # Also try fallbacks for USB drives that fail with "operation not
        # supported" or "not a device of type" — some bridges respond to
        # specific -d flags even when the generic open fails.
        if not needs_fallback and is_usb:
            needs_fallback = True

        if needs_fallback:
            for fallback_args in USB_FALLBACK_CHAIN:
                flag_name = fallback_args[-1]  # e.g. "sat" or "sat,12"
                types_tried.append(flag_name)
                logger.info(
                    "Retrying SMART with '-d %s' for %s (USB bridge fallback).",
                    flag_name, device,
                )
                try:
                    retry_proc = invoke(fallback_args)
                except SmartctlTimeout:
                    logger.debug("-d %s timed out for %s, skipping.", flag_name, device)
                    continue

                retry_stderr = (retry_proc.stderr or "").lower()

                # If this mode says "not a device of type 'scsi'" the OS
                # won't let any SCSI-based passthrough work — stop early.
                if any(p in retry_stderr for p in _DEVICE_NOT_SCSI_PHRASES):
                    logger.debug(
                        "-d %s got device-not-scsi for %s, stopping fallback chain.",
                        flag_name, device,
                    )
                    break

                if retry_proc.returncode in (0, 2):
                    proc = retry_proc
                    device_type_used = flag_name
                    stderr_lower = retry_stderr
                    break
            else:
                # Exhausted all fallbacks without success or early break.
                pass

    # If all USB attempts failed, raise a specific USB error.
    if proc.returncode not in (0, 2) and len(types_tried) > 1:
        raise UsbBridgeBlocked(device, types_tried=types_tried)

    # Classify non-USB failures.
    if proc.returncode not in (0, 2):
        unsupported_phrases = [
            "smart support is: un",
            "device lacks smart capability",
            "smart support is: unavailable",
            "transport error",
        ]
        if any(t in stderr_lower for t in unsupported_phrases):
            raise SmartNotSupported(device, detail=proc.stderr.strip())
        raise SmartctlProtocolError(device, proc.returncode, proc.stderr)

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SmartctlProtocolError(
            device, proc.returncode, f"Failed to parse JSON: {exc}"
        )

    # Extract smartctl version if present.
    version = None
    sv = data.get("smartctl", {})
    if isinstance(sv, dict):
        ver_list = sv.get("version")
        if isinstance(ver_list, list) and ver_list:
            version = ".".join(str(v) for v in ver_list)

    warnings: list[str] = []
    if proc.returncode == 2:
        warnings.append("smartctl reported a non-fatal ATA/SMART command failure (exit 2).")
    if device_type_used:
        warnings.append(f"SMART data retrieved using -d {device_type_used} (USB bridge mode).")

    return CollectionResult(
        data=data,
        device=device,
        retried_with_sat=device_type_used is not None,
        device_type_used=device_type_used,
        device_types_tried=types_tried,
        smartctl_version=version,
        exit_code=proc.returncode,
        stderr=proc.stderr,
        warnings=warnings,
    )
