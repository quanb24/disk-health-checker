"""Main application window — assembles all widgets and wires signals."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStatusBar, QFrame, QProgressBar,
)
from PySide6.QtCore import Qt, QTimer

from disk_health_checker import __version__
from disk_health_checker.models.smart_types import SmartSnapshot, VerdictResult

from .widgets.drive_selector import DriveSelector
from .widgets.verdict_banner import VerdictBanner
from .widgets.findings_list import FindingsList
from .widgets.next_steps_panel import NextStepsPanel
from .worker import ScanWorker


def _section_header(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("section_header")
    return label


def _separator() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet("background-color: #2a2a2a; border: none;")
    return line


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Disk Health Checker v{__version__}")
        self.setMinimumSize(580, 560)
        self.resize(700, 740)

        self._worker: ScanWorker | None = None
        self._last_snapshot: SmartSnapshot | None = None
        self._scan_device: str = ""

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ---- App header ----
        header_frame = QWidget()
        header_frame.setStyleSheet("background-color: #181818;")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 12, 20, 12)

        title = QLabel("Disk Health Checker")
        title.setObjectName("app_title")
        header_layout.addWidget(title)

        header_layout.addStretch()

        version_label = QLabel(f"v{__version__}")
        version_label.setObjectName("app_subtitle")
        header_layout.addWidget(version_label)

        root.addWidget(header_frame)

        # ---- Progress bar (hidden until scan) ----
        self._progress = QProgressBar()
        self._progress.setFixedHeight(3)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setStyleSheet(
            "QProgressBar { background: #1e1e1e; border: none; }"
            "QProgressBar::chunk { background: #3d6fa5; }"
        )
        self._progress.hide()
        root.addWidget(self._progress)

        # ---- Content area ----
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 16, 20, 16)

        # Drive selection
        layout.addWidget(_section_header("SELECT DRIVE"))
        self._drive_selector = DriveSelector()
        layout.addWidget(self._drive_selector)

        # Scan button
        self._scan_btn = QPushButton("Scan Drive")
        self._scan_btn.setMinimumHeight(42)
        self._scan_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_btn.clicked.connect(self._start_scan)
        layout.addWidget(self._scan_btn)

        layout.addSpacing(2)
        layout.addWidget(_separator())
        layout.addSpacing(2)

        # Results
        layout.addWidget(_section_header("RESULTS"))
        self._verdict_banner = VerdictBanner()
        layout.addWidget(self._verdict_banner)

        layout.addSpacing(2)
        layout.addWidget(_separator())
        layout.addSpacing(2)

        # Findings
        layout.addWidget(_section_header("FINDINGS"))
        self._findings_list = FindingsList()
        self._findings_list.setMinimumHeight(80)
        layout.addWidget(self._findings_list, stretch=1)

        layout.addSpacing(2)
        layout.addWidget(_separator())
        layout.addSpacing(2)

        # Next steps
        self._next_steps = NextStepsPanel()
        layout.addWidget(self._next_steps)

        root.addWidget(content, stretch=1)

        # ---- Status bar ----
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

        # Populate drives on startup
        self._drive_selector.refresh()

    def _start_scan(self):
        device = self._drive_selector.current_device()
        if not device:
            self._status_bar.showMessage("No drive selected.")
            return

        self._scan_device = device

        # Disable controls
        self._scan_btn.setEnabled(False)
        self._scan_btn.setText("Scanning...")
        self._drive_selector.set_enabled(False)

        # Show progress
        self._progress.show()

        # Reset result panels to scanning state
        self._verdict_banner.reset(device)
        self._findings_list.reset()
        self._next_steps.reset()
        self._status_bar.showMessage(f"Scanning {device}...")

        # Launch background worker
        self._worker = ScanWorker(device)
        self._worker.finished.connect(self._on_scan_complete)
        self._worker.error.connect(self._on_scan_error)
        self._worker.start()

    def _on_scan_complete(self, snapshot: SmartSnapshot, verdict: VerdictResult):
        self._last_snapshot = snapshot
        self._progress.hide()

        self._verdict_banner.update_verdict(verdict, snapshot)
        self._findings_list.update_findings(verdict.findings, verdict.evidence_missing)
        self._next_steps.update_steps(verdict)

        model = snapshot.model or "Unknown"
        kind = snapshot.device_kind.value.upper()
        self._status_bar.showMessage(
            f"Scan complete — {model} ({kind}) — {verdict.verdict.value}"
        )

        self._restore_controls()

    def _on_scan_error(self, message: str):
        self._progress.hide()

        self._verdict_banner.show_error(message)
        self._findings_list.show_error(message)
        self._next_steps.show_error("Resolve the error above, then try again.")
        self._status_bar.showMessage("Scan failed")

        self._restore_controls()

    def _restore_controls(self):
        self._scan_btn.setEnabled(True)
        self._scan_btn.setText("Scan Drive")
        self._drive_selector.set_enabled(True)
        self._worker = None
