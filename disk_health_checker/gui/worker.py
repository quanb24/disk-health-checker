"""Background worker for SMART scans.

Runs collection + parsing + evaluation in a QThread so the UI stays responsive.
Emits typed signals with results or error messages.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QThread, Signal

from disk_health_checker.checks.smart import collect_and_interpret
from disk_health_checker.checks.smart.errors import SmartctlError, UsbBridgeBlocked
from disk_health_checker.models.smart_types import SmartSnapshot, VerdictResult


class ScanWorker(QThread):
    """Run a SMART scan in the background.

    Signals:
        finished(SmartSnapshot, VerdictResult) — scan completed successfully.
        usb_blocked(str, list) — USB enclosure blocking SMART (device, types_tried).
        error(str) — scan failed with a user-displayable message.
    """

    finished = Signal(object, object)  # (SmartSnapshot, VerdictResult)
    usb_blocked = Signal(str, list)    # (device, types_tried)
    error = Signal(str)

    def __init__(self, device: str, *, transport: str | None = None, parent=None):
        super().__init__(parent)
        self.device = device
        self.transport = transport

    def run(self):
        try:
            snapshot, verdict = collect_and_interpret(
                self.device, transport=self.transport,
            )
        except UsbBridgeBlocked as exc:
            self.usb_blocked.emit(exc.device, exc.types_tried)
            return
        except SmartctlError as exc:
            self.error.emit(str(exc))
            return
        except Exception as exc:
            self.error.emit(f"Unexpected error: {exc}")
            return

        self.finished.emit(snapshot, verdict)
