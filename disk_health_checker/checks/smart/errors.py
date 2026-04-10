"""Typed exceptions for smartctl collection.

Each exception maps to a specific failure mode so the caller can produce
targeted user guidance instead of a generic "something went wrong".
"""

from __future__ import annotations


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


class SmartctlProtocolError(SmartctlError):
    """smartctl returned a non-zero exit and we could not classify the cause."""

    def __init__(self, device: str, returncode: int, stderr: str) -> None:
        self.device = device
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(
            f"smartctl exited with code {returncode} for {device}: {stderr.strip()}"
        )
