"""Sweep editor: VAR1 range, scale, direction, integration, hold/delay times.

Start/stop fields take their unit from the current VAR1 channel (V when the
VAR1 channel is V-sourcing, A when I-sourcing). The owning ``SetupEditor``
calls :meth:`set_var1_unit` whenever the channel panel announces a
structural change, so the labels track the editor live.
"""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QWidget,
)

from ...models.measurement import (
    IntegrationTime,
    SweepDirection,
    SweepMeasurement,
    SweepRange,
    SweepScale,
)
from ._si_float_edit import SiFloatEdit


class SweepPanel(QGroupBox):
    """Editor for ``SweepMeasurement`` (VAR1 only — VAR2 / VAR1' come later)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Sweep (VAR1)", parent)

        self._start = SiFloatEdit(0.0, unit="V", parent=self)
        self._stop = SiFloatEdit(1.0, unit="V", parent=self)

        self._points = QSpinBox(self)
        self._points.setRange(2, 99_999)
        self._points.setValue(21)

        self._scale = QComboBox(self)
        for scale in SweepScale:
            self._scale.addItem(scale.value, scale)

        self._direction = QComboBox(self)
        for direction in SweepDirection:
            self._direction.addItem(direction.value, direction)

        self._integration = QComboBox(self)
        for it in IntegrationTime:
            self._integration.addItem(it.value, it)
        self._integration.setCurrentIndex(
            self._integration.findData(IntegrationTime.MEDIUM)
        )

        self._hold = SiFloatEdit(0.0, unit="s", parent=self)
        self._delay = SiFloatEdit(0.0, unit="s", parent=self)

        form = QFormLayout(self)
        form.addRow("Start", self._start)
        form.addRow("Stop", self._stop)
        form.addRow("Points", self._points)
        form.addRow("Scale", self._scale)
        form.addRow("Direction", self._direction)
        form.addRow("Integration", self._integration)
        form.addRow("Hold time", self._hold)
        form.addRow("Delay time", self._delay)

    # -- public API ----------------------------------------------------------

    def populate_from(self, measurement: SweepMeasurement) -> None:
        self._start.set_value(measurement.var1.start)
        self._stop.set_value(measurement.var1.stop)
        self._points.setValue(measurement.var1.points)
        self._scale.setCurrentIndex(self._scale.findData(measurement.var1.scale))
        self._direction.setCurrentIndex(
            self._direction.findData(measurement.var1.direction)
        )
        self._integration.setCurrentIndex(
            self._integration.findData(measurement.integration)
        )
        self._hold.set_value(measurement.hold_time)
        self._delay.set_value(measurement.delay_time)

    def current_measurement(self) -> SweepMeasurement:
        scale = self._scale.currentData()
        direction = self._direction.currentData()
        integration = self._integration.currentData()
        assert isinstance(scale, SweepScale)
        assert isinstance(direction, SweepDirection)
        assert isinstance(integration, IntegrationTime)
        return SweepMeasurement(
            var1=SweepRange(
                start=self._start.value(),
                stop=self._stop.value(),
                points=self._points.value(),
                scale=scale,
                direction=direction,
            ),
            integration=integration,
            hold_time=self._hold.value(),
            delay_time=self._delay.value(),
        )

    def set_var1_unit(self, unit: str) -> None:
        """Change the unit suffix on the start/stop fields.

        Hold / delay time fields stay in seconds — they are independent of
        the VAR1 source mode.
        """
        self._start.set_unit(unit)
        self._stop.set_unit(unit)


__all__ = ["SweepPanel"]
