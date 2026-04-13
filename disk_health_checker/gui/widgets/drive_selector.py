"""Drive selector combo box with refresh button.

Disk enumeration runs on a background thread to avoid blocking the
Qt event loop when subprocess calls (diskutil, lsblk) are slow.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QHBoxLayout, QComboBox, QPushButton
from PySide6.QtCore import Signal, QThread, QObject

from disk_health_checker.utils.disks import list_disks, DiskInfo


class _DiskEnumerator(QObject):
    """Worker that runs list_disks() off the main thread."""

    finished = Signal(list)

    def run(self):
        disks = list_disks()
        self.finished.emit(disks)


class DriveSelector(QWidget):
    """Combo box listing detected drives with a refresh button."""

    drive_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._disks: list[DiskInfo] = []
        self._enum_thread: QThread | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._combo = QComboBox()
        self._combo.setMinimumWidth(350)
        self._combo.setMinimumHeight(32)
        self._combo.currentIndexChanged.connect(self._on_selection_changed)
        layout.addWidget(self._combo, stretch=1)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setObjectName("refresh_btn")
        self._refresh_btn.setMinimumHeight(32)
        self._refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(self._refresh_btn)

    def refresh(self):
        """Re-enumerate disks on a background thread."""
        if self._enum_thread is not None and self._enum_thread.isRunning():
            return  # Already enumerating — debounce

        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem("Scanning drives...")
        self._combo.blockSignals(False)
        self._refresh_btn.setEnabled(False)

        # Clean up previous worker/thread if they exist
        if self._enum_thread is not None:
            self._enum_thread.deleteLater()

        self._enum_thread = QThread()
        self._worker = _DiskEnumerator()
        self._worker.moveToThread(self._enum_thread)
        self._enum_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_disks_loaded)
        self._worker.finished.connect(self._cleanup_thread)
        self._enum_thread.start()

    def _cleanup_thread(self):
        """Clean up worker and thread after enumeration completes."""
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._enum_thread is not None:
            self._enum_thread.quit()
            self._enum_thread.deleteLater()
            self._enum_thread = None

    def _on_disks_loaded(self, disks: list):
        """Slot called on main thread when enumeration finishes."""
        self._disks = disks
        self._refresh_btn.setEnabled(True)

        self._combo.blockSignals(True)
        self._combo.clear()

        if not self._disks:
            self._combo.addItem("No disks detected \u2014 use CLI with --device")
        else:
            for d in self._disks:
                location = "internal" if d.is_internal else "external" if d.is_external else ""
                model = d.model or "Unknown"
                label = f"{d.device_node}  \u2014  {model}  ({d.size_human})"
                if location:
                    label += f"  [{location}]"
                self._combo.addItem(label)

        self._combo.blockSignals(False)
        if self._disks:
            self._on_selection_changed(0)

    def _on_selection_changed(self, index: int):
        if 0 <= index < len(self._disks):
            self.drive_selected.emit(self._disks[index].device_node)

    def current_device(self) -> str | None:
        idx = self._combo.currentIndex()
        if 0 <= idx < len(self._disks):
            return self._disks[idx].device_node
        return None

    def current_transport(self) -> str | None:
        """Return the bus protocol of the selected drive (e.g. "USB", "NVMe")."""
        idx = self._combo.currentIndex()
        if 0 <= idx < len(self._disks):
            return self._disks[idx].protocol
        return None

    def set_enabled(self, enabled: bool):
        self._combo.setEnabled(enabled)
        self._refresh_btn.setEnabled(enabled)
