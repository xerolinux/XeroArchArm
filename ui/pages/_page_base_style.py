"""Shared page stylesheet : import BASE_STYLE in each page."""

BASE_STYLE = """
QWidget        { background: transparent; color: #e8e8e8; }
QLabel         { color: #c0c0c8; font-size: 13px; background: transparent; }

QLabel#page-title { font-size: 18px; font-weight: bold; color: #e8e8e8; }
QLabel#page-desc  { color: #888890; font-size: 13px; }
QLabel#section    { color: #5b9bd5; font-size: 12px; font-weight: bold; padding-top: 12px; }
QLabel#hint       { color: #888890; font-size: 11px; }
QLabel#key        { color: #888890; font-size: 13px; }
QLabel#value      { color: #e8e8e8; font-size: 13px; }

QLineEdit, QTextEdit, QSpinBox {
    background: rgba(22, 22, 24, 200);
    border: 1px solid rgba(95, 95, 112, 230);
    color: #e8e8e8;
    padding: 6px 10px;
    font-size: 13px;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus { border: 1px solid #5b9bd5; }
QSpinBox::up-button, QSpinBox::down-button {
    background: rgba(62, 62, 74, 220);
    border: none;
    width: 18px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: rgba(80, 80, 96, 240); }

QPushButton {
    background: rgba(52, 52, 64, 220);
    color: #e0e0e8;
    border: 1px solid rgba(100, 100, 118, 220);
    padding: 6px 16px;
    font-size: 13px;
}
QPushButton:hover {
    background: rgba(68, 68, 82, 240);
    border: 1px solid rgba(130, 130, 150, 240);
}
QPushButton:pressed { background: rgba(38, 38, 48, 240); }
QPushButton:disabled { color: #505060; border: 1px solid rgba(62, 62, 72, 140); }

QListWidget {
    background: rgba(22, 22, 24, 200);
    border: 1px solid rgba(62, 62, 72, 180);
    color: #e8e8e8;
    font-size: 13px;
}
QListWidget::item          { padding: 10px; border-bottom: 1px solid rgba(42,42,46,200); }
QListWidget::item:selected { background: rgba(45, 58, 74, 200); color: #e8e8e8; }
QListWidget::item:hover    { background: rgba(37, 37, 48, 200); }

QCheckBox         { color: #e8e8e8; font-size: 13px; spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    background: rgba(22, 22, 24, 200);
    border: 1px solid rgba(62, 62, 72, 180);
}
QCheckBox::indicator:checked { background: #5b9bd5; border: 1px solid #5b9bd5; }

QProgressBar {
    background: rgba(22, 22, 24, 200);
    border: 1px solid rgba(62, 62, 72, 180);
    color: #e8e8e8;
    text-align: center;
    height: 22px;
}
QProgressBar::chunk { background: #5b9bd5; }

QFrame[frameShape="4"] { color: rgba(62,62,72,160); }  /* HLine */

QTabWidget::pane {
    border: 1px solid rgba(62, 62, 72, 160);
    background: transparent;
    top: -1px;
}
QTabBar::tab {
    background: rgba(28, 28, 32, 200);
    color: #888890;
    padding: 6px 18px;
    border: 1px solid rgba(62, 62, 72, 160);
    border-bottom: none;
    font-size: 12px;
}
QTabBar::tab:selected {
    background: rgba(36, 36, 40, 220);
    color: #e8e8e8;
    border-bottom: 2px solid #5b9bd5;
}
QTabBar::tab:hover:!selected { background: rgba(42, 42, 50, 200); color: #c0c0c8; }
"""

WARNING_BOX = """
    color: #f0ad4e;
    font-size: 12px;
    background: rgba(45, 42, 30, 180);
    border: 1px solid rgba(240, 173, 78, 140);
    padding: 8px 12px;
"""

DANGER_BOX = """
    color: #d9534f;
    font-size: 12px;
    font-weight: bold;
    background: rgba(45, 26, 26, 180);
    border: 1px solid rgba(217, 83, 79, 140);
    padding: 7px 12px;
"""

EJECT_BOX = """
    color: #f0ad4e;
    font-size: 13px;
    background: rgba(45, 42, 30, 180);
    border: 1px solid rgba(240, 173, 78, 140);
    padding: 10px 14px;
"""
