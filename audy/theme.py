"""Colours, fonts and the application stylesheet."""

from PySide6.QtGui import QColor, QFont, QFontDatabase

BG = "#0E1014"
SURFACE = "#161920"
SURFACE_2 = "#1C2028"
SURFACE_3 = "#242934"
BORDER = "#252A34"
TEXT = "#ECEEF2"
MUTED = "#8B92A1"
FAINT = "#5A6170"

ACCENT = "#4FE3B5"  # running
AMBER = "#F2B84B"  # paused
SKY = "#7AA7FF"  # outside active hours
RED = "#FF6B6B"  # errors

STATE_COLORS = {"off": FAINT, "running": ACCENT, "paused": AMBER, "waiting": SKY}


def rgb(hex_color):
    c = QColor(hex_color)
    return c.red(), c.green(), c.blue()


def qcolor(hex_color, alpha=255):
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


def _first_family(candidates):
    families = set(QFontDatabase.families())
    for f in candidates:
        if f in families:
            return f
    return candidates[-1]


_ui_family = None
_icon_family = None


def ui_family():
    global _ui_family
    if _ui_family is None:
        _ui_family = _first_family(["Segoe UI Variable Text", "Segoe UI"])
    return _ui_family


def display_family():
    return _first_family(["Segoe UI Variable Display", ui_family()])


def icon_family():
    global _icon_family
    if _icon_family is None:
        _icon_family = _first_family(["Segoe Fluent Icons", "Segoe MDL2 Assets"])
    return _icon_family


def font(size, weight=QFont.Weight.Normal, display=False):
    f = QFont(display_family() if display else ui_family())
    f.setPixelSize(size)
    f.setWeight(weight)
    return f


def icon_font(size):
    f = QFont(icon_family())
    f.setPixelSize(size)
    return f


# Segoe Fluent Icons code points (identical in Segoe MDL2 Assets).
class Icon:
    SETTINGS = ""
    BACK = ""
    POWER = ""
    REFRESH = ""
    PAUSE = ""
    PLAY = ""
    PULSE = ""  # volume / sound
    SPEAKER = ""
    CHEVRON_DOWN = ""
    MOON = ""
    WARNING = ""
    SKIP = ""  # music note-ish
    INFO = ""


def stylesheet():
    ui = ui_family()
    return f"""
* {{
    font-family: "{ui}";
    color: {TEXT};
    outline: none;
}}
QWidget#root, QStackedWidget, QWidget#page {{
    background: {BG};
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background: transparent;
    border: none;
}}
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#divider {{
    background: {BORDER};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QLabel {{ background: transparent; }}
QLabel#muted {{ color: {MUTED}; }}
QLabel#faint {{ color: {FAINT}; }}
QLabel#section {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}

QPushButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 14px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{ background: {SURFACE_3}; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled {{ color: {FAINT}; }}
QPushButton::menu-indicator {{ image: none; width: 0; }}

QPushButton#iconButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0;
    color: {MUTED};
}}
QPushButton#iconButton:hover {{ background: {SURFACE_2}; color: {TEXT}; }}
QPushButton#iconButton:pressed {{ background: {SURFACE}; }}

QSlider {{ min-height: 22px; }}
QSlider::groove:horizontal {{
    height: 4px;
    background: {SURFACE_3};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {TEXT};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{ background: #FFFFFF; }}
QSlider::sub-page:horizontal:disabled {{ background: {FAINT}; }}

QComboBox {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 5px 12px;
    font-size: 13px;
    min-width: 52px;
}}
QComboBox:hover {{ background: {SURFACE_3}; }}
QComboBox:disabled {{ color: {FAINT}; background: {SURFACE}; }}
QComboBox::drop-down {{ width: 0; border: none; }}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    selection-background-color: {SURFACE_3};
    padding: 4px;
    outline: none;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 4px 2px 4px 0;
}}
QScrollBar::handle:vertical {{
    background: {SURFACE_3};
    border-radius: 3px;
    min-height: 32px;
}}
QScrollBar::handle:vertical:hover {{ background: {FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    height: 0; background: none;
}}

QMenu {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 26px 7px 14px;
    border-radius: 6px;
    font-size: 13px;
}}
QMenu::item:selected {{ background: {SURFACE_3}; }}
QMenu::item:disabled {{ color: {MUTED}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 5px 8px; }}

QToolTip {{
    background: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 5px 8px;
    border-radius: 6px;
}}
"""
