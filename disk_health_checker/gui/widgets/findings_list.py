"""Scrollable list of SMART findings with severity cards.

Findings are sorted: FAIL first, then WARN, then INFO.
Each finding is a visually distinct card with a colored severity indicator.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
)
from PySide6.QtCore import Qt

from disk_health_checker.models.smart_types import Finding, FindingSeverity


_SEVERITY_CONFIG = {
    FindingSeverity.FAIL: {
        "label": "FAIL",
        "accent": "#ef5350",
        "bg": "#2d1a1a",
        "border": "#5a2020",
    },
    FindingSeverity.WARN: {
        "label": "WARN",
        "accent": "#ffb74d",
        "bg": "#2d2818",
        "border": "#5a4420",
    },
    FindingSeverity.INFO: {
        "label": "INFO",
        "accent": "#78909c",
        "bg": "#262626",
        "border": "#3a3a3a",
    },
}

_SEVERITY_ORDER = {
    FindingSeverity.FAIL: 0,
    FindingSeverity.WARN: 1,
    FindingSeverity.INFO: 2,
}


def _make_finding_card(f: Finding) -> QFrame:
    cfg = _SEVERITY_CONFIG.get(f.severity, _SEVERITY_CONFIG[FindingSeverity.INFO])

    card = QFrame()
    card.setStyleSheet(
        f"background-color: {cfg['bg']}; "
        f"border: 1px solid {cfg['border']}; "
        f"border-left: 3px solid {cfg['accent']}; "
        f"border-radius: 5px;"
    )

    layout = QHBoxLayout(card)
    layout.setContentsMargins(10, 7, 10, 7)
    layout.setSpacing(10)

    badge = QLabel(cfg["label"])
    badge.setFixedWidth(38)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    bf = badge.font()
    bf.setPointSize(9)
    bf.setBold(True)
    badge.setFont(bf)
    badge.setStyleSheet(f"color: {cfg['accent']}; background: transparent; border: none;")
    layout.addWidget(badge)

    msg = QLabel(f.message)
    msg.setWordWrap(True)
    msg.setStyleSheet("color: #ddd; background: transparent; border: none;")
    layout.addWidget(msg, stretch=1)

    return card


class FindingsList(QScrollArea):
    """Displays a sorted list of finding cards, or a placeholder."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._layout.setSpacing(5)
        self._layout.setContentsMargins(0, 0, 4, 0)
        self.setWidget(self._container)

        self._show_placeholder(
            "No scan results yet",
            "Results will appear here after scanning a drive.",
        )

    def update_findings(self, findings: list[Finding], evidence_missing: list[str]):
        self._clear()

        if not findings and not evidence_missing:
            self._show_placeholder(
                "No significant warnings detected",
                "All readable SMART signals are within normal range.",
                accent="#4caf50",
            )
            return

        sorted_findings = sorted(
            findings, key=lambda f: _SEVERITY_ORDER.get(f.severity, 99)
        )
        for f in sorted_findings:
            self._layout.addWidget(_make_finding_card(f))

        if evidence_missing:
            gap = QFrame()
            gap.setStyleSheet(
                "background-color: #232323; border: 1px solid #333; "
                "border-left: 3px solid #555; border-radius: 5px;"
            )
            gl = QHBoxLayout(gap)
            gl.setContentsMargins(10, 7, 10, 7)
            gl.setSpacing(10)
            badge = QLabel("GAP")
            badge.setFixedWidth(38)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bf = badge.font()
            bf.setPointSize(9)
            bf.setBold(True)
            badge.setFont(bf)
            badge.setStyleSheet("color: #666; background: transparent; border: none;")
            gl.addWidget(badge)
            msg = QLabel(f"Signals missing: {', '.join(evidence_missing)}")
            msg.setWordWrap(True)
            msg.setStyleSheet("color: #888; background: transparent; border: none;")
            gl.addWidget(msg, stretch=1)
            self._layout.addWidget(gap)

    def show_usb_blocked(self, types_tried: list[str] | None = None):
        """Show an informative card explaining USB enclosure blocking."""
        self._clear()
        card = QFrame()
        card.setStyleSheet(
            "background-color: #2d2818; border: 1px solid #5a4a2a; "
            "border-left: 3px solid #ffb74d; border-radius: 5px;"
        )
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(6)

        header = QLabel("USB Enclosure Blocking SMART")
        hf = header.font()
        hf.setBold(True)
        header.setFont(hf)
        header.setStyleSheet("color: #ffb74d; background: transparent; border: none;")
        cl.addWidget(header)

        explanation = QLabel(
            "The USB-to-SATA bridge chip inside this enclosure is preventing "
            "SMART health data from being read. The drive itself is likely fine "
            "— this is a common hardware limitation."
        )
        explanation.setWordWrap(True)
        explanation.setStyleSheet("color: #bbb; background: transparent; border: none;")
        cl.addWidget(explanation)

        if types_tried:
            tried = QLabel(f"Modes attempted: {', '.join(types_tried)}")
            tried.setStyleSheet("color: #888; background: transparent; border: none; font-size: 11px;")
            cl.addWidget(tried)

        self._layout.addWidget(card)

    def show_error(self, message: str):
        self._clear()
        card = QFrame()
        card.setStyleSheet(
            "background-color: #2d1a1a; border: 1px solid #5a2020; "
            "border-left: 3px solid #ef5350; border-radius: 5px;"
        )
        cl = QHBoxLayout(card)
        cl.setContentsMargins(10, 10, 10, 10)
        cl.setSpacing(10)
        badge = QLabel("ERR")
        badge.setFixedWidth(38)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bf = badge.font()
        bf.setPointSize(9)
        bf.setBold(True)
        badge.setFont(bf)
        badge.setStyleSheet("color: #ef5350; background: transparent; border: none;")
        cl.addWidget(badge)
        msg = QLabel(message)
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #ddd; background: transparent; border: none;")
        cl.addWidget(msg, stretch=1)
        self._layout.addWidget(card)

    def reset(self):
        self._clear()
        self._show_placeholder("Scanning...", "Reading SMART data from drive.")

    def _clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _show_placeholder(self, title: str, subtitle: str = "", accent: str = "#555"):
        wrapper = QWidget()
        wrapper.setStyleSheet("background: transparent;")
        wl = QVBoxLayout(wrapper)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.setSpacing(4)
        wl.setContentsMargins(0, 16, 0, 16)

        t = QLabel(title)
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tf = t.font()
        tf.setPointSize(13)
        t.setFont(tf)
        t.setStyleSheet(f"color: {accent};")
        wl.addWidget(t)

        if subtitle:
            s = QLabel(subtitle)
            s.setAlignment(Qt.AlignmentFlag.AlignCenter)
            s.setStyleSheet("color: #555; font-size: 12px;")
            wl.addWidget(s)

        self._layout.addWidget(wrapper)
