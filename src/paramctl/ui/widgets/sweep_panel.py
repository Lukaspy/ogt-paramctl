"""Sweep editor: VAR1 range, scale, direction, integration, hold/delay times."""
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
from ._float_edit import FloatEdit


class SweepPanel(QGroupBox):
    """Editor for ``SweepMeasurement`` (VAR1 only — VAR2 / VAR1' come later)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Sweep (VAR1)", parent)

        self._start = FloatEdit(0.0, self)
        self._stop = FloatEdit(1.0, self)

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

        self._hold = FloatEdit(0.0, self)
        self._delay = FloatEdit(0.0, self)

        form = QFormLayout(self)
        form.addRow("Start", self._start)
        form.addRow("Stop", self._stop)
        form.addRow("Points", self._points)
        form.addRow("Scale", self._scale)
        form.addRow("Direction", self._direction)
        form.addRow("Integration", self._integration)
        form.addRow("Hold time (s)", self._hold)
        form.addRow("Delay time (s)", self._delay)

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


__all__ = ["SweepPanel"]
