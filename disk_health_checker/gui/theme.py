"""Application-wide dark theme stylesheet.

Neutral dark palette — professional, readable, not gamer-aesthetic.
Individual widgets override specific properties as needed.
"""

DARK_STYLESHEET = """
/* ---- Global ---- */
QMainWindow, QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-family: "Helvetica Neue", "Segoe UI", sans-serif;
    font-size: 13px;
}

/* ---- Cards / grouped panels ---- */
QFrame[frameShape="6"] {
    /* StyledPanel */
    background-color: #2a2a2a;
    border: 1px solid #3a3a3a;
    border-radius: 8px;
}

/* ---- Combo box ---- */
QComboBox {
    background-color: #2a2a2a;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 7px 12px;
    color: #e0e0e0;
    min-height: 24px;
}
QComboBox:hover {
    border-color: #5a5a5a;
}
QComboBox:focus {
    border-color: #3d6fa5;
}
QComboBox::drop-down {
    border: none;
    width: 24px;
}
QComboBox QAbstractItemView {
    background-color: #2a2a2a;
    color: #e0e0e0;
    selection-background-color: #3d6fa5;
    border: 1px solid #444;
    outline: none;
}

/* ---- Primary button (scan) ---- */
QPushButton {
    background-color: #3d6fa5;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #4a82bc;
}
QPushButton:pressed {
    background-color: #2d5a8a;
}
QPushButton:disabled {
    background-color: #2a2a2a;
    color: #555;
    border: 1px solid #333;
}

/* ---- Secondary button (refresh) ---- */
QPushButton#refresh_btn {
    background-color: transparent;
    color: #999;
    font-weight: normal;
    padding: 7px 14px;
    border: 1px solid #444;
    border-radius: 6px;
}
QPushButton#refresh_btn:hover {
    background-color: #333;
    color: #ccc;
    border-color: #555;
}
QPushButton#refresh_btn:pressed {
    background-color: #2a2a2a;
}

/* ---- Scroll area ---- */
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #444;
    border-radius: 3px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #555;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

/* ---- Status bar ---- */
QStatusBar {
    background-color: #181818;
    color: #777;
    font-size: 11px;
    padding: 4px 12px;
    border-top: 1px solid #2a2a2a;
}

/* ---- Section headers ---- */
QLabel#section_header {
    color: #777;
    font-size: 10px;
    font-weight: bold;
    letter-spacing: 1.5px;
    padding: 0;
    margin: 0;
}

/* ---- App title label ---- */
QLabel#app_title {
    color: #e0e0e0;
    font-size: 16px;
    font-weight: bold;
    background: transparent;
}
QLabel#app_subtitle {
    color: #666;
    font-size: 11px;
    background: transparent;
}
"""
