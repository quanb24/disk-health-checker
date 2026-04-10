"""Large color-coded verdict display with drive info summary."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QFrame
from PySide6.QtCore import Qt

from disk_health_checker.models.smart_types import (
    SmartSnapshot, Verdict, VerdictResult, Confidence,
)

# (fg_text, bg, border_accent)
_COLORS = {
    Verdict.PASS:    ("#4caf50", "#1b3a1b", "#2e7d32"),
    Verdict.WARNING: ("#ffb74d", "#3a2e1a", "#e65100"),
    Verdict.FAIL:    ("#ef5350", "#3a1a1a", "#c62828"),
    Verdict.UNKNOWN: ("#888888", "#252525", "#444444"),
}

_VERDICT_DESCRIPTIONS = {
    Verdict.PASS:    "Drive appears healthy",
    Verdict.WARNING: "Warning signs detected — monitor closely",
    Verdict.FAIL:    "Critical problems — take action now",
    Verdict.UNKNOWN: "Could not determine health — this is NOT the same as healthy",
}


def _format_age(hours: int) -> str:
    if hours >= 8760:
        return f"~{hours / 8760:.1f} years"
    if hours >= 24:
        return f"~{hours // 24:,} days"
    return f"{hours} hours"


class VerdictBanner(QFrame):
    """Displays verdict, score, confidence, and drive identity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumHeight(110)

        layout = QVBoxLayout(self)
        layout.setSpacing(3)
        layout.setContentsMargins(20, 14, 20, 14)

        # Row 1: verdict + score
        top = QHBoxLayout()
        top.setSpacing(12)

        self._verdict_label = QLabel("")
        font = self._verdict_label.font()
        font.setPointSize(30)
        font.setBold(True)
        self._verdict_label.setFont(font)
        top.addWidget(self._verdict_label)

        top.addStretch()

        self._score_label = QLabel("")
        sf = self._score_label.font()
        sf.setPointSize(18)
        self._score_label.setFont(sf)
        self._score_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        top.addWidget(self._score_label)

        layout.addLayout(top)

        # Row 2: description + confidence
        self._desc_label = QLabel("")
        df = self._desc_label.font()
        df.setPointSize(12)
        self._desc_label.setFont(df)
        layout.addWidget(self._desc_label)

        # Row 3: drive info
        self._drive_info = QLabel("")
        inf = self._drive_info.font()
        inf.setPointSize(11)
        self._drive_info.setFont(inf)
        layout.addWidget(self._drive_info)

        self._set_initial()

    def update_verdict(self, vr: VerdictResult, snapshot: SmartSnapshot | None = None):
        fg, _, _ = _COLORS.get(vr.verdict, _COLORS[Verdict.UNKNOWN])

        self._verdict_label.setText(vr.verdict.value)
        self._verdict_label.setStyleSheet(
            f"color: {fg}; background: transparent;"
        )

        self._score_label.setText(f"{vr.score}/100")
        self._score_label.setStyleSheet(
            f"color: {fg}; background: transparent;"
        )

        desc = _VERDICT_DESCRIPTIONS.get(vr.verdict, "")
        self._desc_label.setText(f"{desc}  |  Confidence: {vr.confidence.value}")
        self._desc_label.setStyleSheet("color: #aaa; background: transparent;")

        if snapshot:
            parts = []
            if snapshot.model:
                parts.append(snapshot.model)
            kind = snapshot.device_kind.value.upper()
            if kind and kind != "UNKNOWN":
                parts.append(kind)
            if snapshot.is_ssd is True:
                parts.append("SSD")
            elif snapshot.is_ssd is False:
                parts.append("HDD")
            if snapshot.power_on_hours is not None:
                parts.append(_format_age(snapshot.power_on_hours))
            if snapshot.temperature_c is not None:
                parts.append(f"{snapshot.temperature_c} °C")
            self._drive_info.setText("  ·  ".join(parts))
            self._drive_info.setStyleSheet("color: #777; background: transparent;")
            self._drive_info.show()
        else:
            self._drive_info.hide()

        self._apply_card(vr.verdict)

    def show_usb_blocked(self, device: str = ""):
        """Show a non-alarming UNKNOWN state for USB enclosure blocking."""
        self._verdict_label.setText("UNKNOWN")
        self._verdict_label.setStyleSheet("color: #ffb74d; background: transparent;")
        self._score_label.setText("")
        self._desc_label.setText(
            "USB enclosure is blocking SMART data — "
            "this is a hardware limitation, not a drive failure"
        )
        self._desc_label.setStyleSheet("color: #bbb; background: transparent;")
        if device:
            self._drive_info.setText(f"Device: {device}  ·  Connection: USB")
            self._drive_info.setStyleSheet("color: #777; background: transparent;")
            self._drive_info.show()
        else:
            self._drive_info.hide()
        # Use a warm amber card instead of gray (not alarming) or red (not a failure)
        self.setStyleSheet(
            "VerdictBanner {"
            "  background-color: #2a2518;"
            "  border: 1px solid #5a4a2a;"
            "  border-left: 4px solid #ffb74d;"
            "  border-radius: 8px;"
            "}"
        )

    def show_error(self, message: str):
        self._verdict_label.setText("ERROR")
        self._verdict_label.setStyleSheet("color: #ef5350; background: transparent;")
        self._score_label.setText("")
        self._desc_label.setText(message[:200])
        self._desc_label.setStyleSheet("color: #bbb; background: transparent;")
        self._drive_info.hide()
        self._apply_card(Verdict.UNKNOWN)

    def reset(self, device: str = ""):
        self._verdict_label.setText("Scanning...")
        self._verdict_label.setStyleSheet("color: #3d6fa5; background: transparent;")
        self._score_label.setText("")
        if device:
            self._desc_label.setText(f"Reading SMART data from {device}")
        else:
            self._desc_label.setText("Reading SMART data...")
        self._desc_label.setStyleSheet("color: #666; background: transparent;")
        self._drive_info.hide()
        self._apply_card(Verdict.UNKNOWN)

    def _set_initial(self):
        self._verdict_label.setText("—")
        self._verdict_label.setStyleSheet("color: #444; background: transparent;")
        self._score_label.setText("")
        self._desc_label.setText("Select a drive above and click Scan to begin")
        self._desc_label.setStyleSheet("color: #555; background: transparent;")
        self._drive_info.hide()
        self._apply_card(Verdict.UNKNOWN)

    def _apply_card(self, verdict: Verdict):
        _, bg, border = _COLORS.get(verdict, _COLORS[Verdict.UNKNOWN])
        self.setStyleSheet(
            f"VerdictBanner {{"
            f"  background-color: {bg};"
            f"  border: 1px solid {border};"
            f"  border-left: 4px solid {border};"
            f"  border-radius: 8px;"
            f"}}"
        )
