"""Invoke smartctl and return raw parsed JSON.

This module does I/O only. It does not interpret SMART data.
All interpretation happens in the parsing and evaluation layers.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from disk_health_checker.utils.platform import which, get_platform_info
from .errors import (
    SmartctlNotInstalled,
    SmartctlTimeout,
    SmartNotSupported,
    SmartctlProtocolError,
)

logger = logging.getLogger(__name__)

# Seconds before we give up on smartctl.  A dying drive or stalled USB
# bridge can cause smartctl to block for a very long time.
DEFAULT_TIMEOUT_S = 30


@dataclass
class CollectionResult:
    """Raw smartctl output with metadata about how it was obtained."""
    data: Dict[str, Any]
    device: str
    retried_with_sat: bool = False
    smartctl_version: Optional[str] = None
    exit_code: int = 0
    stderr: str = ""
    warnings: list[str] = field(default_factory=list)


def collect_smart(device: str, *, timeout_s: int = DEFAULT_TIMEOUT_S) -> CollectionResult:
    """Run smartctl and return parsed JSON.

    Uses -H -A -i -j for a concise JSON report.  Retries with '-d sat'
    on common USB-SATA bridge failures (macOS AND Linux).

    Raises:
        SmartctlNotInstalled: smartctl not on PATH.
        SmartctlTimeout: subprocess timed out.
        SmartNotSupported: device/enclosure does not expose SMART.
        SmartctlProtocolError: unclassified non-zero exit.
    """
    smartctl_path = which("smartctl")
    if not smartctl_path:
        raise SmartctlNotInstalled()

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
    retried = False
    stderr_lower = (proc.stderr or "").lower()

    # Retry with -d sat for USB-SATA bridge issues (on any platform).
    sat_retry_phrases = [
        "unknown usb bridge",
        "please specify device type with -d",
        "unable to detect device type",
    ]
    should_retry = proc.returncode != 0 and any(
        phrase in stderr_lower for phrase in sat_retry_phrases
    )
    if should_retry:
        logger.info("Retrying SMART with '-d sat' for %s (USB bridge).", device)
        proc = invoke(["-d", "sat"])
        retried = True
        stderr_lower = (proc.stderr or "").lower()

    # Classify failures.
    # smartctl uses bitmasked exit codes; bit 0 = command parse error,
    # bit 1 = device open failed, bit 2 = SMART/ATA command failed, etc.
    # Codes 0 and 2 (bit 1 set = "some SMART or other ATA command failed")
    # are treated as non-fatal because smartctl can still return valid data.
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

    return CollectionResult(
        data=data,
        device=device,
        retried_with_sat=retried,
        smartctl_version=version,
        exit_code=proc.returncode,
        stderr=proc.stderr,
        warnings=warnings,
    )
