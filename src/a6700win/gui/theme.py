"""统一视觉主题：石墨底色 + 琥珀强调色，克制的卡片式布局。"""
from __future__ import annotations

BACKGROUND = "#0b0d11"
SURFACE = "#14171d"
SURFACE_HIGH = "#1b1f27"
BORDER = "#262b34"
BORDER_SOFT = "#1f242c"
TEXT = "#e7eaf0"
TEXT_MUTED = "#98a0ad"
TEXT_FAINT = "#6b7482"
ACCENT = "#e0a340"
ACCENT_SOFT = "#2a2317"
SUCCESS = "#4ec9a0"
DANGER = "#ef6a6a"
WARNING = "#f0b429"

FONT_STACK = '"Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif'

STYLESHEET = f"""
QWidget {{
    background: {BACKGROUND};
    color: {TEXT};
    font-family: {FONT_STACK};
    font-size: 13px;
}}
QLabel, QCheckBox, QToolButton, QRadioButton {{
    background: transparent;
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: #333a45; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QLabel#Title {{ font-size: 26px; font-weight: 600; }}
QLabel#Subtitle {{ color: {TEXT_MUTED}; font-size: 13px; }}
QLabel#SectionTitle {{ font-size: 15px; font-weight: 600; }}
QLabel#Muted {{ color: {TEXT_MUTED}; }}
QLabel#Faint {{ color: {TEXT_FAINT}; font-size: 12px; }}
QLabel#StepChip {{ color: {ACCENT}; font-size: 12px; font-weight: 600; letter-spacing: 0.6px; }}
QFrame#Footer {{ background: {SURFACE}; border-top: 1px solid {BORDER_SOFT}; }}
QLabel#Badge {{
    background: {ACCENT_SOFT};
    color: {ACCENT};
    border: 1px solid #3a3018;
    border-radius: 9px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 600;
}}

QFrame#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER_SOFT};
    border-radius: 12px;
}}
QFrame#Card:hover {{ border-color: {BORDER}; }}
QFrame#Inset {{
    background: {BACKGROUND};
    border: 1px solid {BORDER_SOFT};
    border-radius: 9px;
}}
QFrame#Divider {{ background: {BORDER_SOFT}; max-height: 1px; border: none; }}

QPushButton {{
    background: {SURFACE_HIGH};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
}}
QPushButton:hover {{ background: #232833; border-color: #34404f; }}
QPushButton:pressed {{ background: #1a1e25; }}
QPushButton:disabled {{ color: {TEXT_FAINT}; background: #14171c; border-color: {BORDER_SOFT}; }}
QPushButton#Primary {{
    background: {ACCENT};
    color: #17130a;
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton#Primary:hover {{ background: #eab558; }}
QPushButton#Primary:disabled {{ background: #2c2618; color: #7d6d4b; border-color: #3a3018; }}
QPushButton#Ghost {{
    background: transparent;
    border: 1px solid {BORDER_SOFT};
    color: {TEXT_MUTED};
}}
QPushButton#Ghost:hover {{ color: {TEXT}; border-color: {BORDER}; }}
QPushButton#Link {{
    background: transparent;
    border: none;
    color: {ACCENT};
    padding: 2px 0;
    text-align: left;
}}
QPushButton#Link:hover {{ color: #f2c372; }}

QCheckBox {{ spacing: 9px; color: {TEXT}; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 1px solid #3a4250;
    background: {BACKGROUND};
}}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox:disabled {{ color: {TEXT_FAINT}; }}

QPlainTextEdit, QTextEdit {{
    background: {BACKGROUND};
    border: 1px solid {BORDER_SOFT};
    border-radius: 8px;
    color: {TEXT_MUTED};
    font-family: "Cascadia Mono", "Consolas", monospace;
    font-size: 12px;
    padding: 6px;
}}
QComboBox {{
    background: {SURFACE_HIGH};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 10px;
    min-width: 180px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE_HIGH};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_SOFT};
    selection-color: {ACCENT};
}}
QProgressBar {{
    background: {BORDER_SOFT};
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QToolTip {{
    background: {SURFACE_HIGH};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 5px 8px;
}}
"""

LEVEL_COLORS = {"scope": ACCENT, "info": TEXT_MUTED, "risk": DANGER}


def state_color(state: str) -> str:
    return {"enabled": SUCCESS, "disabled": TEXT_FAINT, "unknown": WARNING}.get(state, TEXT_MUTED)
