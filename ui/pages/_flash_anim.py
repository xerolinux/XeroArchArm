"""Animated USB → lightning bolt → SD card graphic for Confirm page."""
import math

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF
from PySide6.QtGui import (
    QBrush, QColor, QLinearGradient, QPainter,
    QPainterPath, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QSizePolicy, QWidget


class FlashAnimWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._tick = 0
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(120)
        t = QTimer(self)
        t.timeout.connect(self._advance)
        t.start(40)  # 25 fps

    def _advance(self):
        self._tick += 1
        self.update()

    # ── paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.translate(self.width() / 2, self.height() / 2 - 25)
        s = min(self.width() / 380, self.height() / 170)
        p.scale(s, s)

        tick = self._tick
        pulse      = 0.5 + 0.5 * math.sin(tick * 0.10)
        bolt_flash = 0.5 + 0.5 * math.sin(tick * 0.22)
        rx_glow    = max(0.0, math.sin(tick * 0.10 - 1.2))

        self._draw_cables(p, pulse)
        self._draw_particles(p, tick)
        self._draw_usb(p)
        self._draw_sd(p, rx_glow)
        self._draw_bolt_halo(p, bolt_flash)
        self._draw_bolt(p, bolt_flash)
        p.end()

    # ── sub-elements ──────────────────────────────────────────────────────────

    def _draw_cables(self, p, pulse):
        a = int(70 + 50 * pulse)
        pen = QPen(QColor(91, 155, 213, a), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(-104, 0), QPointF(-50, 0))
        p.drawLine(QPointF(50, 0),   QPointF(104, 0))

    def _draw_particles(self, p, tick):
        p.setPen(Qt.NoPen)
        offsets = [0.0, 0.2, 0.4, 0.6, 0.8]
        for off in offsets:
            phase = (tick * 0.035 + off) % 1.0
            x = -100 + phase * 200
            fade = min(phase * 6, 1.0, (1.0 - phase) * 6)
            if fade <= 0:
                continue
            r = 2.5 + 1.5 * math.sin(phase * math.pi)
            a = int(220 * fade)
            p.setBrush(QBrush(QColor(0, 210, 255, a)))
            p.drawEllipse(QPointF(x, 0), r, r)

    def _draw_usb(self, p):
        x = -136
        # Body
        p.setPen(QPen(QColor(155, 155, 168), 1.5))
        p.setBrush(QBrush(QColor(58, 58, 72)))
        p.drawRoundedRect(QRectF(x - 24, -18, 48, 36), 4, 4)
        # Inner slot
        p.setPen(QPen(QColor(28, 28, 38), 1))
        p.setBrush(QBrush(QColor(22, 22, 32)))
        p.drawRoundedRect(QRectF(x - 16, -10, 32, 20), 2, 2)
        # USB trident
        col = QColor(188, 188, 200)
        p.setPen(QPen(col, 1.5))
        p.setBrush(Qt.NoBrush)
        # stem
        p.drawLine(QPointF(x, -8), QPointF(x, 8))
        # left branch + circle
        p.drawLine(QPointF(x, -5), QPointF(x - 7, -9))
        p.setBrush(QBrush(col))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(x - 7, -10), 2.5, 2.5)
        # right branch + square
        p.setPen(QPen(col, 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(x, 3), QPointF(x + 7, 3))
        p.setPen(QPen(col, 1.2))
        p.drawRect(QRectF(x + 6, 0, 5, 6))
        # Cable stub
        p.setPen(QPen(QColor(100, 100, 112), 6))
        p.drawLine(QPointF(x + 24, 0), QPointF(x + 42, 0))

    def _draw_sd(self, p, rx_glow):
        x = 136
        # SD card shape — notched top-left corner
        path = QPainterPath()
        path.moveTo(x - 16, -22)
        path.lineTo(x + 16, -22)
        path.lineTo(x + 16,  22)
        path.lineTo(x - 16,  22)
        path.lineTo(x - 16, -14)
        path.lineTo(x - 8,  -22)
        path.closeSubpath()

        edge_col = QColor(
            int(91 + 164 * rx_glow),
            int(155 + 100 * rx_glow),
            213,
            220,
        )
        fill_col = QColor(14, 32, 58)
        p.setPen(QPen(edge_col, 1.8))
        p.setBrush(QBrush(fill_col))
        p.drawPath(path)

        # Gold contacts
        p.setPen(QPen(QColor(200, 168, 60), 1.8))
        for gx in [x - 11, x - 7, x - 3, x + 1, x + 5, x + 9, x + 13]:
            p.drawLine(QPointF(gx, 6), QPointF(gx, 22))

        # Label lines
        la = int(100 + 100 * rx_glow)
        p.setPen(QPen(QColor(91, 155, 213, la), 1))
        p.drawLine(QPointF(x - 9, -10), QPointF(x + 12, -10))
        p.drawLine(QPointF(x - 9,  -4), QPointF(x + 7,   -4))

        # Rx glow halo
        if rx_glow > 0.05:
            rg = QRadialGradient(QPointF(x, 0), 32)
            rg.setColorAt(0, QColor(91, 200, 255, int(80 * rx_glow)))
            rg.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(rg))
            p.drawEllipse(QPointF(x, 0), 32, 32)

        # Cable stub
        p.setPen(QPen(QColor(100, 100, 112), 6))
        p.drawLine(QPointF(x - 24, 0), QPointF(x - 42, 0))

    def _draw_bolt_halo(self, p, bright):
        rg = QRadialGradient(QPointF(0, 0), 56)
        rg.setColorAt(0,   QColor(255, 220, 20,  int(130 * bright)))
        rg.setColorAt(0.4, QColor(180, 80,  255, int(70  * bright)))
        rg.setColorAt(1,   QColor(0,   0,   0,   0))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(rg))
        r = 50 + 10 * bright
        p.drawEllipse(QPointF(0, 0), r, r)

    def _draw_bolt(self, p, bright):
        # Classic 8-point lightning bolt (clockwise)
        path = QPainterPath()
        pts = [
            QPointF(6,  -42),  # top-left
            QPointF(20, -42),  # top-right
            QPointF(6,   -2),  # mid-right after top diagonal
            QPointF(18,  -2),  # notch step right
            QPointF(4,   42),  # bottom-right
            QPointF(-10, 42),  # bottom-left
            QPointF(-4,   2),  # mid-left before notch
            QPointF(-16,  2),  # notch step left
        ]
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        path.closeSubpath()

        # Outer soft glow stroke
        gp = QPen(QColor(255, 200, 0, int(90 * bright)), 7)
        gp.setJoinStyle(Qt.RoundJoin)
        p.setPen(gp)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # Filled bolt with gradient
        lg = QLinearGradient(QPointF(-10, -42), QPointF(10, 42))
        lg.setColorAt(0, QColor(255, 240, 80,  int(230 + 25 * bright)))
        lg.setColorAt(1, QColor(255, 140, 0,   int(200 + 30 * bright)))
        p.setPen(QPen(QColor(255, 255, 160, 180), 1))
        p.setBrush(QBrush(lg))
        p.drawPath(path)

        # Inner bright core (slim highlight down the center)
        core = QPainterPath()
        core.moveTo(7,  -34)
        core.lineTo(14, -4)
        core.lineTo(8,  -4)
        core.lineTo(12,  34)
        core.lineTo(6,   6)
        core.lineTo(0,   6)
        core.closeSubpath()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 220, int(160 * bright))))
        p.drawPath(core)
