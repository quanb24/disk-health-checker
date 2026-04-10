"""GUI entry point for disk-health-checker.

Launch with:
    python -m disk_health_checker.gui
    disk-health-checker-gui          (after pip install -e ".[gui]")

Requires PySide6: pip install disk-health-checker[gui]
"""

from __future__ import annotations

import sys


def main():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is required for the GUI.\n"
            "Install it with: pip install disk-health-checker[gui]",
            file=sys.stderr,
        )
        sys.exit(1)

    from .main_window import MainWindow
    from .theme import DARK_STYLESHEET

    app = QApplication(sys.argv)
    app.setApplicationName("Disk Health Checker")
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
