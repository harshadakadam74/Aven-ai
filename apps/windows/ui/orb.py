"""Animated assistant orb (idle / thinking / speaking / listening / error)."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QTimer, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QRadialGradient
from PySide6.QtWidgets import QWidget

_STATE_COLORS = {
    "idle": ("#22d3ee", "#7c3aed"),
    "listening": ("#22d3ee", "#38bdf8"),
    "thinking": ("#a78bfa", "#7c3aed"),
    "speaking": ("#22d3ee", "#a78bfa"),
    "error": ("#f87171", "#b91c1c"),
}
_STATE_SPEED = {"idle": 0.04, "listening": 0.10, "thinking": 0.16, "speaking": 0.12, "error": 0.02}


class OrbWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(140, 140)
        self._state = "idle"
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(33)

    def set_state(self, state: str) -> None:
        self._state = state if state in _STATE_COLORS else "idle"
        self.update()

    def _tick(self) -> None:
        self._phase += _STATE_SPEED[self._state]
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        size = min(self.width(), self.height())
        center = QPointF(self.width() / 2, self.height() / 2)
        pulse = 1.0 + 0.06 * math.sin(self._phase)
        radius = size * 0.34 * pulse
        inner, outer = _STATE_COLORS[self._state]

        glow = QRadialGradient(center, radius * 1.9)
        glow_color = QColor(inner)
        glow_color.setAlpha(70)
        glow.setColorAt(0.0, glow_color)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawEllipse(center, radius * 1.9, radius * 1.9)

        body = QRadialGradient(center - QPointF(radius * 0.3, radius * 0.3), radius * 1.3)
        body.setColorAt(0.0, QColor(inner))
        body.setColorAt(1.0, QColor(outer))
        painter.setBrush(QBrush(body))
        painter.drawEllipse(center, radius, radius)
