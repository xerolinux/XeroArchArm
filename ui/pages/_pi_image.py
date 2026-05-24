"""Shared Pi4 image widget with purple glow + drop shadow."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy, QGraphicsDropShadowEffect

_PI4_PNG = str(Path(__file__).resolve().parent.parent.parent / 'assets' / 'Pi4.png')


class PiImageWidget(QLabel):
    """Scales Pi4.png to fill available space; applies purple glow + drop shadow."""

    def __init__(self, max_h: int = 0, parent=None):
        super().__init__(parent)
        self._src = QPixmap(_PI4_PNG)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(80)
        if max_h:
            self.setMaximumHeight(max_h)

        # Combined purple glow + drop shadow (Qt allows one effect per widget)
        fx = QGraphicsDropShadowEffect(self)
        fx.setBlurRadius(30)
        fx.setOffset(0, 4)
        fx.setColor(QColor(148, 60, 220, 200))
        self.setGraphicsEffect(fx)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._src.isNull():
            return
        # Inner margins leave room for the glow bleed so it isn't clipped
        w = max(1, self.width() - 60)
        h = max(1, self.height() - 32)
        px = self._src.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.setPixmap(px)
