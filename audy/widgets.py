"""Custom-painted controls used across the UI."""

import math

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .theme import qcolor


# ---------------------------------------------------------------- power dial


class PowerDial(QWidget):
    """The big round control on the home screen.

    Shows a progress ring for the current interval, a countdown in the
    middle, and emits rings outward whenever a pulse goes out.
    """

    clicked = Signal()

    SIZE = 268
    RING_R = 104

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self._state = "off"
        self._progress = 0.0
        self._title = "Off"
        self._subtitle = "Tap to start"
        self._hover = 0.0
        self._pressed = False
        self._color = QColor(theme.FAINT)
        self._waves = []  # active pulse animations

        self._hover_anim = QVariantAnimation(self, duration=160)
        self._hover_anim.valueChanged.connect(self._set_hover)
        self._color_anim = QVariantAnimation(self, duration=420)
        self._color_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._color_anim.valueChanged.connect(self._set_color)

    def sizeHint(self):
        return QSize(self.SIZE, self.SIZE)

    # -------------------------------------------------- state

    def set_state(self, state, title, subtitle, progress):
        if state != self._state:
            self._state = state
            self._color_anim.stop()
            self._color_anim.setStartValue(self._color)
            self._color_anim.setEndValue(QColor(theme.STATE_COLORS[state]))
            self._color_anim.start()
        self._title, self._subtitle, self._progress = title, subtitle, progress
        self.update()

    def pulse(self):
        anim = QVariantAnimation(self, duration=1700, startValue=0.0, endValue=1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self.update)
        anim.finished.connect(lambda a=anim: self._waves.remove(a) if a in self._waves else None)
        self._waves.append(anim)
        anim.start()

        # A second, delayed ring for a softer "ripple" feel.
        follow = QVariantAnimation(self, duration=1700, startValue=-0.18, endValue=1.0)
        follow.setEasingCurve(QEasingCurve.Type.OutCubic)
        follow.valueChanged.connect(self.update)
        follow.finished.connect(lambda a=follow: self._waves.remove(a) if a in self._waves else None)
        self._waves.append(follow)
        follow.start()

    def _set_hover(self, v):
        self._hover = v
        self.update()

    def _set_color(self, c):
        self._color = c
        self.update()

    # -------------------------------------------------- input

    def enterEvent(self, e):
        self._animate_hover(1.0)

    def leaveEvent(self, e):
        self._animate_hover(0.0)
        self._pressed = False
        self.update()

    def _animate_hover(self, target):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(target)
        self._hover_anim.start()

    def _inside(self, pos):
        c = QPointF(self.width() / 2, self.height() / 2)
        return math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= self.RING_R + 6

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._inside(e.position()):
            self._pressed = True
            self.update()

    def mouseReleaseEvent(self, e):
        if self._pressed and self._inside(e.position()):
            self.clicked.emit()
        self._pressed = False
        self.update()

    # -------------------------------------------------- paint

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        R = self.RING_R
        color = QColor(self._color)
        live = self._state != "off"

        # Ambient glow behind the dial.
        if live:
            glow = QRadialGradient(c, R + 30)
            glow.setColorAt(0.0, qcolor(color.name(), 46))
            glow.setColorAt(0.65, qcolor(color.name(), 16))
            glow.setColorAt(1.0, qcolor(color.name(), 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(glow)
            p.drawEllipse(c, R + 30, R + 30)

        # Outgoing pulse rings.
        for anim in self._waves:
            t = anim.currentValue()
            if t is None or t <= 0:
                continue
            radius = R + 4 + t * 30
            alpha = int(150 * (1 - t) ** 1.6)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(qcolor(color.name(), alpha), 2.0))
            p.drawEllipse(c, radius, radius)

        # Disc.
        inner = R - 14
        scale = 0.985 if self._pressed else 1.0
        disc = QRadialGradient(QPointF(c.x(), c.y() - inner * 0.6), inner * 1.6)
        top = QColor(theme.SURFACE_3).lighter(100 + int(12 * self._hover))
        disc.setColorAt(0, top)
        disc.setColorAt(1, QColor(theme.SURFACE))
        p.setPen(QPen(QColor(255, 255, 255, 14 + int(10 * self._hover)), 1))
        p.setBrush(disc)
        p.drawEllipse(c, inner * scale, inner * scale)

        # Track + progress ring.
        track = QPen(QColor(theme.SURFACE_2), 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(track)
        p.setBrush(Qt.BrushStyle.NoBrush)
        ring = QRectF(c.x() - R, c.y() - R, 2 * R, 2 * R)
        p.drawEllipse(ring)

        if live:
            frac = self._progress if self._state == "running" else 1.0
            pen = QPen(color, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            if self._state != "running":
                color.setAlpha(110)
                pen.setColor(color)
            p.setPen(pen)
            span = -max(0.004, frac) * 360 * 16
            p.drawArc(ring, 90 * 16, int(span))
            if self._state == "running":
                ang = math.radians(90 - frac * 360)
                dot = QPointF(c.x() + R * math.cos(ang), c.y() - R * math.sin(ang))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(theme.TEXT))
                p.drawEllipse(dot, 4.5, 4.5)
            color.setAlpha(255)

        # Centre content.
        p.setPen(color if live else QColor(theme.MUTED).lighter(100 + int(25 * self._hover)))
        p.setFont(theme.icon_font(22))
        p.drawText(QRectF(c.x() - 30, c.y() - 58, 60, 30), Qt.AlignmentFlag.AlignCenter, theme.Icon.POWER)

        p.setPen(QColor(theme.TEXT))
        title_size = 40 if self._state == "running" else 30
        p.setFont(theme.font(title_size, QFont.Weight.DemiBold, display=True))
        p.drawText(QRectF(c.x() - inner, c.y() - 26, inner * 2, 50), Qt.AlignmentFlag.AlignCenter, self._title)

        p.setPen(QColor(theme.MUTED))
        p.setFont(theme.font(12))
        p.drawText(QRectF(c.x() - inner, c.y() + 26, inner * 2, 20), Qt.AlignmentFlag.AlignCenter, self._subtitle)
        p.end()


# ---------------------------------------------------------------- toggle switch


class ToggleSwitch(QAbstractButton):
    W, H = 42, 24

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.W, self.H)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self, duration=150)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def get_knob(self):
        return self._pos

    def set_knob(self, v):
        self._pos = v
        self.update()

    knob = Property(float, get_knob, set_knob)

    def sizeHint(self):
        return QSize(self.W, self.H)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        off, on = QColor(theme.SURFACE_3), QColor(theme.ACCENT)
        if not self.isEnabled():
            on = QColor(theme.FAINT)
        t = self._pos
        track = QColor(
            int(off.red() + (on.red() - off.red()) * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue() + (on.blue() - off.blue()) * t),
        )
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, 0, self.W, self.H), self.H / 2, self.H / 2)
        d = self.H - 6
        x = 3 + t * (self.W - d - 6)
        p.setBrush(QColor("#0E1014") if t > 0.5 else QColor(theme.TEXT))
        p.drawEllipse(QRectF(x, 3, d, d))
        p.end()


# ---------------------------------------------------------------- segmented control


class Segmented(QWidget):
    changed = Signal(str)

    def __init__(self, options, current, parent=None):
        """options: list of (key, label)."""
        super().__init__(parent)
        self._options = options
        self._index = max(0, [k for k, _ in options].index(current)) if current in dict(options) else 0
        self._x = float(self._index)
        self._hover = -1
        self.setFixedHeight(34)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._anim = QVariantAnimation(self, duration=180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_x)

    def _set_x(self, v):
        self._x = v
        self.update()

    def current(self):
        return self._options[self._index][0]

    def _seg_w(self):
        return (self.width() - 6) / len(self._options)

    def _at(self, x):
        i = int((x - 3) // self._seg_w())
        return min(len(self._options) - 1, max(0, i))

    def mouseMoveEvent(self, e):
        h = self._at(e.position().x())
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        i = self._at(e.position().x())
        if i == self._index:
            return
        self._anim.stop()
        self._anim.setStartValue(self._x)
        self._anim.setEndValue(float(i))
        self._anim.start()
        self._index = i
        self.changed.emit(self.current())
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(QColor(theme.SURFACE_2))
        p.drawRoundedRect(r, 10, 10)
        w = self._seg_w()
        pill = QRectF(3 + self._x * w, 3, w, self.height() - 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.SURFACE_3).lighter(115))
        p.drawRoundedRect(pill, 8, 8)
        p.setFont(theme.font(12, QFont.Weight.Medium))
        for i, (_, label) in enumerate(self._options):
            seg = QRectF(3 + i * w, 3, w, self.height() - 6)
            if i == self._index:
                p.setPen(QColor(theme.TEXT))
            elif i == self._hover:
                p.setPen(QColor(theme.TEXT).darker(115))
            else:
                p.setPen(QColor(theme.MUTED))
            p.drawText(seg, Qt.AlignmentFlag.AlignCenter, label)
        p.end()


# ---------------------------------------------------------------- layout helpers


def icon_button(glyph, size=34, glyph_px=15, tooltip=""):
    b = QPushButton(glyph)
    b.setObjectName("iconButton")
    b.setFont(theme.icon_font(glyph_px))
    b.setFixedSize(size, size)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        b.setToolTip(tooltip)
    return b


def card():
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 6, 16, 6)
    lay.setSpacing(0)
    return f, lay


def divider():
    d = QFrame()
    d.setObjectName("divider")
    return d


def section_label(text):
    lab = QLabel(text.upper())
    lab.setObjectName("section")
    return lab


def label(text, size=13, weight=QFont.Weight.Normal, role=None):
    lab = QLabel(text)
    lab.setFont(theme.font(size, weight))
    if role:
        lab.setObjectName(role)
    return lab


class SettingRow(QWidget):
    """Title (+ optional description) on the left, a control on the right."""

    def __init__(self, title, description=None, control=None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 11, 0, 11)
        lay.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = label(title, 13, QFont.Weight.Medium)
        text.addWidget(self.title)
        self.description = None
        if description:
            self.description = label(description, 12, role="muted")
            self.description.setWordWrap(True)
            text.addWidget(self.description)
        lay.addLayout(text, 1)
        if control is not None:
            lay.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)


class ElidedLabel(QLabel):
    """A single-line label that trims with an ellipsis instead of widening its parent."""

    def __init__(self, text, size=13, role=None, parent=None):
        super().__init__(parent)
        self._full = text
        self.setFont(theme.font(size))
        if role:
            self.setObjectName(role)
        self.setToolTip(text)
        self.setMinimumWidth(10)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.setText(self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideRight, self.width()))


class EventDot(QWidget):
    def __init__(self, color, parent=None):
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(8, 8)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(QRectF(0, 0, 8, 8))
        p.end()


class Spark(QWidget):
    """A tiny bar strip of recent pulse/skip activity."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self._bars = []

    def set_bars(self, kinds):
        self._bars = kinds[-28:]
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = 28
        gap = 3
        w = (self.width() - gap * (n - 1)) / n
        colors = {"pulse": theme.ACCENT, "skip": theme.SKY, "error": theme.RED}
        pad = n - len(self._bars)
        for i in range(n):
            x = i * (w + gap)
            if i < pad:
                p.setBrush(QColor(theme.SURFACE_2))
                h = 6
            else:
                kind = self._bars[i - pad]
                p.setBrush(QColor(colors.get(kind, theme.FAINT)))
                h = {"pulse": 20, "skip": 12, "error": 20}.get(kind, 6)
            p.setPen(Qt.PenStyle.NoPen)
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, self.height() - h, w, h), 2, 2)
            p.drawPath(path)
        p.end()
