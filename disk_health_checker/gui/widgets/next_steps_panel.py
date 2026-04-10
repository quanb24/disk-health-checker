"""Panel displaying actionable next-step recommendations.

Critical actions (FAIL verdict) are visually emphasized.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt

from disk_health_checker.models.smart_types import Verdict, VerdictResult


_RECOMMENDATIONS = {
    Verdict.PASS: [
        "No action needed. Keep regular backups as always.",
    ],
    Verdict.WARNING: [
        "Keep backups current. This drive is usable but has warning signs.",
        "Re-run this check in ~30 days to monitor for progression.",
        "Avoid using this drive as sole storage for irreplaceable data.",
    ],
    Verdict.FAIL: [
        "Back up all data from this drive immediately.",
        "Replace the drive before returning it to service.",
        "Do not use this drive as sole storage for any important data.",
    ],
    Verdict.UNKNOWN: [
        "Could not determine drive health — do not assume it is safe.",
        "Try connecting the drive directly via SATA (not USB) and re-scanning.",
        "If behind a RAID controller, use the vendor diagnostic tool instead.",
    ],
}

_ACCENT = {
    Verdict.PASS: "#4caf50",
    Verdict.WARNING: "#ffb74d",
    Verdict.FAIL: "#ef5350",
    Verdict.UNKNOWN: "#888",
}


class NextStepsPanel(QFrame):
    """Displays numbered recommendations with verdict-colored emphasis."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "NextStepsPanel {"
            "  background-color: #232323;"
            "  border: 1px solid #333;"
            "  border-radius: 8px;"
            "}"
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 10, 16, 10)
        self._layout.setSpacing(2)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._header = QLabel("NEXT STEPS")
        self._header.setObjectName("section_header")
        self._header.setStyleSheet(
            "color: #777; background: transparent; border: none; "
            "font-size: 10px; font-weight: bold; letter-spacing: 1.5px;"
        )
        self._layout.addWidget(self._header)

        self._steps = QVBoxLayout()
        self._steps.setSpacing(2)
        self._layout.addLayout(self._steps)

    def update_steps(self, vr: VerdictResult):
        self._clear_steps()
        steps = _RECOMMENDATIONS.get(vr.verdict, _RECOMMENDATIONS[Verdict.UNKNOWN])
        accent = _ACCENT.get(vr.verdict, "#888")

        for i, step in enumerate(steps, 1):
            label = QLabel(f"{i}.  {step}")
            label.setWordWrap(True)

            if vr.verdict == Verdict.FAIL and i == 1:
                label.setStyleSheet(
                    f"color: {accent}; font-weight: bold; "
                    f"background: transparent; border: none; "
                    f"padding: 3px 0; font-size: 13px;"
                )
            else:
                label.setStyleSheet(
                    "color: #bbb; background: transparent; border: none; "
                    "padding: 2px 0;"
                )
            self._steps.addWidget(label)

    def show_error(self, message: str):
        self._clear_steps()
        label = QLabel(f"1.  {message}")
        label.setWordWrap(True)
        label.setStyleSheet(
            "color: #ef5350; background: transparent; border: none;"
        )
        self._steps.addWidget(label)

    def reset(self):
        self._clear_steps()

    def _clear_steps(self):
        while self._steps.count():
            item = self._steps.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
