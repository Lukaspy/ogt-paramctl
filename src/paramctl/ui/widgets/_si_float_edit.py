"""``QLineEdit`` that parses and displays SI-prefixed numeric values.

Solves the "compliance is unreadable in scientific notation" problem:
``1e-3`` round-trips to ``"1 mA"`` for an A-unit field. Users can type
either the SI form (``"100 u"``, ``"1.5 m"``) or the scientific form
(``"1.5e-3"``); both parse to the same value, and on edit-finished the
field is re-rendered in canonical SI form.
"""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QWidget

from ...util.units import format_si, parse_si


class SiFloatEdit(QLineEdit):
    """Float field with SI-prefix input and best-prefix display.

    Attributes:
        value_changed: Emitted with the new SI-base value whenever the user
            commits an edit that changes the stored value.
    """

    value_changed = pyqtSignal(float)

    def __init__(
        self,
        value: float = 0.0,
        *,
        unit: str = "",
        decimals: int = 4,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._value = float(value)
        self._unit = unit
        self._decimals = decimals
        self._render()
        self.editingFinished.connect(self._on_finished)

    def value(self) -> float:
        """Current value in SI base units (volts, amps, seconds, …)."""
        return self._value

    def set_value(self, v: float) -> None:
        """Set the value programmatically; redraws the field."""
        new_value = float(v)
        if new_value != self._value:
            self._value = new_value
        self._render()

    def unit(self) -> str:
        """Currently-displayed unit suffix (e.g. ``"A"``)."""
        return self._unit

    def set_unit(self, unit: str) -> None:
        """Change the unit suffix and redraw without altering the value."""
        if unit == self._unit:
            return
        self._unit = unit
        self._render()

    def _render(self) -> None:
        self.setText(format_si(self._value, decimals=self._decimals, unit=self._unit))

    def _on_finished(self) -> None:
        try:
            new_value = parse_si(self.text())
        except ValueError:
            self._render()
            return
        if new_value != self._value:
            self._value = new_value
            self.value_changed.emit(self._value)
        self._render()


__all__ = ["SiFloatEdit"]
