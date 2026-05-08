"""A ``QLineEdit`` subclass that accepts float input incl. scientific notation.

``QDoubleSpinBox`` cannot parse ``1e-3`` out of the box, which is awkward for
instrument control where compliance values are routinely sub-microamp. This
small wrapper keeps the field free-form while still validating on edit.
"""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import QLineEdit, QWidget


class FloatEdit(QLineEdit):
    """Line-edit for a float value. Accepts ``1e-3``, ``-2.5``, ``0.001`` etc."""

    value_changed = pyqtSignal(float)

    def __init__(self, value: float = 0.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        validator = QDoubleValidator(self)
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        self.setValidator(validator)
        self.set_value(value)
        self.editingFinished.connect(self._emit_value)

    def value(self) -> float:
        text = self.text().strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0

    def set_value(self, v: float) -> None:
        self.setText(f"{v:g}")

    def _emit_value(self) -> None:
        self.value_changed.emit(self.value())


__all__ = ["FloatEdit"]
