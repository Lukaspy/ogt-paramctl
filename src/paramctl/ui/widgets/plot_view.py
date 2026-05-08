"""Live measurement plot built on pyqtgraph.

Renders one curve per measured channel. Samples accumulate as they arrive;
``reset()`` clears the curves and starts a new run. The widget is dumb —
it knows nothing about drivers, engines, or threads. The MainWindow feeds
it ``Sample`` instances via signal-slot connections.
"""
from __future__ import annotations

import logging
from typing import Any

import pyqtgraph as pg
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ...models.channel import ChannelConfig, ChannelFunction, ChannelMode
from ...models.results import Sample
from ...models.setup import Setup

logger = logging.getLogger(__name__)


_CURVE_COLOURS = ["y", "c", "m", "g", "r", "w"]


class PlotView(QWidget):
    """Plots ``Sample`` data live as it arrives from the engine.

    Each non-VAR1 channel listed in the active ``Setup`` gets its own curve;
    the X axis is the VAR1 source value, the Y axis is the channel reading
    (current when V-sourcing, voltage when I-sourcing). For M0, all measured
    channels share an axis — multi-axis plotting is a follow-up.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plot = pg.PlotWidget()
        self._plot.setBackground("k")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.addLegend()
        self._plot.setLabel("bottom", "VAR1", units="V")
        self._plot.setLabel("left", "I", units="A")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

        self._curves: dict[Any, pg.PlotDataItem] = {}
        self._x: list[float] = []
        self._y: dict[Any, list[float]] = {}
        self._var1_label: str | None = None

    def configure_for(self, setup: Setup) -> None:
        """Tear down existing curves and create one per measured channel.

        Call this immediately before a new run so the plot reflects the
        setup's channel layout.
        """
        self._plot.clear()
        # ``clear()`` removes the legend item; rebuild.
        self._plot.addLegend()
        self._curves = {}
        self._x = []
        self._y = {}

        var1 = self._var1(setup)
        self._var1_label = self._axis_label(var1, axis="bottom")
        self._plot.setLabel("bottom", self._var1_label)

        plotted_any = False
        for index, channel in enumerate(_measured_channels(setup)):
            colour = _CURVE_COLOURS[index % len(_CURVE_COLOURS)]
            label = channel.label or channel.channel_id.value
            curve = self._plot.plot(
                pen=pg.mkPen(colour, width=2), name=label, symbol="o", symbolSize=4
            )
            self._curves[channel.channel_id] = curve
            self._y[channel.channel_id] = []
            plotted_any = True

        if plotted_any:
            sample_unit = "A" if any(
                c.mode is ChannelMode.V_SOURCE for c in setup.channels
            ) else "V"
            self._plot.setLabel("left", "Reading", units=sample_unit)

    def add_sample(self, sample: Sample) -> None:
        """Append a sample's readings to each configured curve."""
        if sample.var1_value is None:
            return
        self._x.append(sample.var1_value)
        for channel_id, curve in self._curves.items():
            value = sample.readings.get(channel_id)
            if value is None:
                continue
            self._y[channel_id].append(value)
            # Curves can have fewer Y points than X if a channel goes missing.
            xs = self._x[: len(self._y[channel_id])]
            curve.setData(xs, self._y[channel_id])

    def clear_curves(self) -> None:
        """Empty all curves but keep their definitions in place."""
        self._x = []
        for ch_id in self._y:
            self._y[ch_id] = []
        for curve in self._curves.values():
            curve.setData([], [])

    @staticmethod
    def _var1(setup: Setup) -> ChannelConfig:
        return next(
            c for c in setup.channels if c.function is ChannelFunction.VAR1
        )

    @staticmethod
    def _axis_label(channel: ChannelConfig, *, axis: str) -> str:
        del axis
        unit = "V" if channel.mode is ChannelMode.V_SOURCE else "A"
        name = channel.label or channel.channel_id.value
        return f"{name} ({unit})"


def _measured_channels(setup: Setup) -> list[ChannelConfig]:
    """Channels we plot a curve for — currently the VAR1 channel only.

    The driver layer presently only requests measurement on the VAR1
    channel (``MM 2,<var1>``); when multi-channel measurement lands, this
    function expands to include companion measurement channels.
    """
    return [c for c in setup.channels if c.function is ChannelFunction.VAR1]


__all__ = ["PlotView"]
