"""Spotify/iOS-style toggle switch — replaces a checkable QPushButton.
Animates the knob, emits toggled(bool) on click or keyboard activation.
"""
from __future__ import annotations

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QKeyEvent, QMouseEvent, QPainter
from PySide6.QtWidgets import QWidget

from gui import theme


class ToggleSwitch(QWidget):
    """A 44×24 px pill toggle. Track turns Spotify green when on, knob slides."""

    toggled = Signal(bool)

    TRACK_W = 44
    TRACK_H = 24
    KNOB_R = 10           # knob radius
    PAD = 2               # gap between knob and track edge

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._knob_x = self._target_knob_x(checked)
        self.setFixedSize(QSize(self.TRACK_W, self.TRACK_H))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._anim = QPropertyAnimation(self, b"knobX", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ---------- public API ----------

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, on: bool) -> None:
        if on == self._checked:
            return
        self._checked = on
        self._anim.stop()
        self._anim.setStartValue(self._knob_x)
        self._anim.setEndValue(self._target_knob_x(on))
        self._anim.start()
        self.toggled.emit(on)

    def toggle(self) -> None:
        self.setChecked(not self._checked)

    # ---------- Qt Property for animation ----------

    def _get_knob_x(self) -> float:
        return self._knob_x

    def _set_knob_x(self, x: float) -> None:
        self._knob_x = x
        self.update()

    knobX = Property(float, _get_knob_x, _set_knob_x)  # noqa: N815

    def _target_knob_x(self, on: bool) -> float:
        if on:
            return self.TRACK_W - self.PAD - self.KNOB_R * 2 + self.KNOB_R
        return self.PAD + self.KNOB_R

    # ---------- input ----------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
            event.accept()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggle()
            event.accept()
        else:
            super().keyPressEvent(event)

    # ---------- painting ----------

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Track
        track_color = QColor(theme.PRIMARY) if self._checked else QColor(theme.SURFACE_4)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(self.rect(), self.TRACK_H / 2, self.TRACK_H / 2)
        # Knob
        knob_color = QColor("#000000") if self._checked else QColor(theme.INK)
        p.setBrush(knob_color)
        cx = int(self._knob_x)
        cy = self.TRACK_H // 2
        p.drawEllipse(cx - self.KNOB_R, cy - self.KNOB_R, self.KNOB_R * 2, self.KNOB_R * 2)
        # Focus ring
        if self.hasFocus():
            p.setPen(QColor(theme.INK))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), self.TRACK_H / 2, self.TRACK_H / 2)
        p.end()
