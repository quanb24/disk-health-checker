"""Typed exceptions for smartctl collection.

Each exception maps to a specific failure mode so the caller can produce
targeted user guidance instead of a generic "something went wrong".
"""

from __future__ import annotations

from typing import List


class SmartctlError(RuntimeError):
    """Base class for all smartctl-related errors."""


class SmartctlNotInstalled(SmartctlError):
    """smartctl binary not found on PATH."""

    def __init__(self) -> None:
        super().__init__(
            "smartctl not found on PATH. "
            "On macOS: 'brew install smartmontools'. "
            "On Linux: 'sudo apt install smartmontools' or equivalent."
        )


class SmartctlTimeout(SmartctlError):
    """smartctl did not respond within the allowed time."""

    def __init__(self, device: str, timeout_s: int) -> None:
        self.device = device
        self.timeout_s = timeout_s
        super().__init__(
            f"smartctl timed out after {timeout_s}s on {device}. "
            "The drive may be unresponsive or behind a stalled USB bridge."
        )


class SmartNotSupported(SmartctlError):
    """Device does not support SMART or bridge blocks pass-through."""

    def __init__(self, device: str, detail: str = "") -> None:
        self.device = device
        msg = (
            f"SMART not available for {device}. "
            "This is common for USB enclosures that do not pass SMART data through. "
            "Try connecting the drive directly or using a different enclosure."
        )
        if detail:
            msg += f" ({detail})"
        super().__init__(msg)


class UsbBridgeBlocked(SmartctlError):
    """USB enclosure confirmed to block all SMART passthrough.

    Raised after the collector exhausts the full USB fallback chain
    (sat, sat12, sat16, usbsunplus, usbjmicron) without success.
    The drive itself is likely fine — the enclosure is the barrier.
    """

    def __init__(self, device: str, *, types_tried: List[str] | None = None) -> None:
        self.device = device
        self.types_tried = types_tried or []
        tried_str = ", ".join(self.types_tried) if self.types_tried else "auto"
        super().__init__(
            f"The USB enclosure for {device} is blocking SMART data. "
            f"Tried device modes: {tried_str} — none succeeded.\n\n"
            "This is a hardware limitation of the USB-to-SATA bridge chip "
            "inside the enclosure, not a problem with the drive itself.\n\n"
            "To read SMART data from this drive:\n"
            "  1. Connect the drive directly via SATA (remove from enclosure)\n"
            "  2. Use a USB dock/adapter that supports SAT passthrough "
            "(e.g. StarTech, Sabrent)\n"
            "  3. Check if your enclosure manufacturer offers a firmware update"
        )


class SmartctlProtocolError(SmartctlError):
    """smartctl returned a non-zero exit and we could not classify the cause."""

    def __init__(self, device: str, returncode: int, stderr: str) -> None:
        self.device = device
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"smartctl exited with code {returncode} for {device}: {stderr.strip()}"
        )
