"""The Audy mark: a source dot with two outgoing waves. Painted, so it scales to any size."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap

from . import theme


def paint_mark(p, rect, color, weight=1.0):
    """Draw the mark inside rect (a square), centred."""
    s = rect.width() / 100.0
    ox, oy = rect.x(), rect.y()

    def pt(x, y):
        return QPointF(ox + x * s, oy + y * s)

    cx, cy = 31.0, 50.0
    stroke = 10.0 * weight
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    r = 11.0
    p.drawEllipse(pt(cx, cy), r * s, r * s)

    pen = QPen(QColor(color), stroke * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    for radius in (25.0, 43.0):
        box = QRectF(pt(cx - radius, cy - radius), pt(cx + radius, cy + radius))
        p.drawArc(box, int(-48 * 16), int(96 * 16))


def tray_pixmap(state, size=64):
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = {"off": "#9AA0AA"}.get(state, theme.STATE_COLORS.get(state, theme.ACCENT))
    # The mark's ink spans ~60% of its box; overscan so it fills small tray slots.
    k = 1.3
    off = -(k - 1) / 2 * size
    paint_mark(p, QRectF(off, off, size * k, size * k), color, weight=1.2)
    p.end()
    return pm


def tray_icon(state):
    icon = QIcon()
    for size in (16, 20, 24, 32, 48, 64):
        icon.addPixmap(tray_pixmap(state, size))
    return icon


def app_pixmap(size):
    """Full app icon: mark on a dark rounded tile."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tile = QRectF(0, 0, size, size).adjusted(size * 0.04, size * 0.04, -size * 0.04, -size * 0.04)
    path = QPainterPath()
    path.addRoundedRect(tile, size * 0.23, size * 0.23)
    grad = QLinearGradient(tile.topLeft(), tile.bottomRight())
    grad.setColorAt(0, QColor("#1E232D"))
    grad.setColorAt(1, QColor("#0E1014"))
    p.fillPath(path, grad)
    p.setPen(QPen(QColor(255, 255, 255, 22), max(1.0, size / 128)))
    p.drawPath(path)
    inset = size * 0.2
    paint_mark(p, QRectF(inset, inset, size - 2 * inset, size - 2 * inset), theme.ACCENT, 1.1)
    p.end()
    return pm


def app_icon():
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(app_pixmap(size))
    return icon
