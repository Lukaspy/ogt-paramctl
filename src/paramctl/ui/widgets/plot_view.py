"""Multi-trace measurement plot built on pyqtgraph.

Each completed run leaves its curves on the plot, recoloured and dimmed so
the active trace is visually distinct. Useful workflow: tweak a parameter,
run, compare against the previous trace; older traces stay visible until
you call ``clear_history()``.

The widget is dumb — it knows nothing about drivers, engines, or threads.
The MainWindow feeds it ``Sample`` instances via signal-slot connections
and calls ``begin_run(setup)`` immediately before each run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pyqtgraph as pg
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ...models.channel import ChannelConfig, ChannelFunction, ChannelId, ChannelMode
from ...models.results import Sample
from ...models.setup import Setup

logger = logging.getLogger(__name__)


# Bright primary colour used for the active (in-progress / most-recent) trace.
_ACTIVE_COLOUR = QColor("yellow")
_ACTIVE_LINE_WIDTH = 2

# Cycled palette for historical traces. Each completed run picks the next
# colour; the alpha is then shaped by age in ``_recolour_history``.
_HISTORY_HUES: tuple[QColor, ...] = (
    QColor(255, 140, 0),    # orange
    QColor(0, 200, 255),    # azure
    QColor(255, 80, 200),   # pink
    QColor(120, 255, 80),   # lime
    QColor(180, 130, 255),  # violet
    QColor(255, 220, 80),   # gold
)
_HISTORY_LINE_WIDTH = 1
# Oldest trace fades down to this alpha. Newer traces interpolate up to
# the full-strength _HISTORY_ALPHA_MAX.
_HISTORY_ALPHA_MIN = 60
_HISTORY_ALPHA_MAX = 200


@dataclass
class _TraceRun:
    """One completed-or-active run's curves on the plot."""

    setup: Setup
    curves: dict[ChannelId, pg.PlotDataItem] = field(default_factory=dict)
    x: list[float] = field(default_factory=list)
    y_by_channel: dict[ChannelId, list[float]] = field(default_factory=dict)


class PlotView(QWidget):
    """Plots ``Sample`` data live with multi-run history."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plot = pg.PlotWidget()
        self._plot.setBackground("k")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._legend = self._plot.addLegend()
        self._plot.setLabel("bottom", "VAR1")
        self._plot.setLabel("left", "Reading")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

        self._history: list[_TraceRun] = []
        self._active: _TraceRun | None = None
        self._run_counter = 0

    # -- run lifecycle -------------------------------------------------------

    def begin_run(self, setup: Setup) -> None:
        """Demote the previous active run to history; create new active curves."""
        if self._active is not None:
            self._history.append(self._active)
            self._active = None
        self._recolour_history()

        self._run_counter += 1
        run = _TraceRun(setup=setup)
        self._configure_axes(setup)

        for channel in _measured_channels(setup):
            label = self._format_label(channel, run_number=self._run_counter)
            curve = self._plot.plot(
                pen=pg.mkPen(_ACTIVE_COLOUR, width=_ACTIVE_LINE_WIDTH),
                name=label,
                symbol="o",
                symbolSize=4,
                symbolBrush=_ACTIVE_COLOUR,
                symbolPen=_ACTIVE_COLOUR,
            )
            run.curves[channel.channel_id] = curve
            run.y_by_channel[channel.channel_id] = []

        self._active = run

    def add_sample(self, sample: Sample) -> None:
        if self._active is None:
            return
        if sample.var1_value is None:
            return
        self._active.x.append(sample.var1_value)
        for channel_id, curve in self._active.curves.items():
            value = sample.readings.get(channel_id)
            if value is None:
                continue
            self._active.y_by_channel[channel_id].append(value)
            xs = self._active.x[: len(self._active.y_by_channel[channel_id])]
            curve.setData(xs, self._active.y_by_channel[channel_id])

    def clear_history(self) -> None:
        """Remove every run from the plot, including the active one."""
        for run in self._history:
            for curve in run.curves.values():
                self._plot.removeItem(curve)
        if self._active is not None:
            for curve in self._active.curves.values():
                self._plot.removeItem(curve)
        self._history = []
        self._active = None
        self._run_counter = 0

    # -- styling -------------------------------------------------------------

    def _configure_axes(self, setup: Setup) -> None:
        var1 = next(c for c in setup.channels if c.function is ChannelFunction.VAR1)
        x_unit = "V" if var1.mode is ChannelMode.V_SOURCE else "A"
        self._plot.setLabel(
            "bottom", var1.label or var1.channel_id.value, units=x_unit
        )

        # Y axis follows the VAR1 mode: V-source measures current, I-source
        # measures voltage. Until multi-channel measurement lands, this stays
        # tied to the VAR1 channel.
        y_unit = "A" if var1.mode is ChannelMode.V_SOURCE else "V"
        self._plot.setLabel("left", "Reading", units=y_unit)

    def _recolour_history(self) -> None:
        """Walk historical curves and reapply colour + alpha based on age.

        Most-recent history runs get the brightest historical colour; older
        runs fade towards _HISTORY_ALPHA_MIN.
        """
        if not self._history:
            return
        n = len(self._history)
        for index, run in enumerate(self._history):
            age_factor = (index + 1) / n  # newest history -> 1.0, oldest -> 1/n
            alpha = int(
                _HISTORY_ALPHA_MIN
                + (_HISTORY_ALPHA_MAX - _HISTORY_ALPHA_MIN) * age_factor
            )
            base_colour = _HISTORY_HUES[index % len(_HISTORY_HUES)]
            colour = QColor(
                base_colour.red(),
                base_colour.green(),
                base_colour.blue(),
                alpha,
            )
            for curve in run.curves.values():
                pen = pg.mkPen(colour, width=_HISTORY_LINE_WIDTH)
                curve.setPen(pen)
                curve.setSymbol(None)

    @staticmethod
    def _format_label(channel: ChannelConfig, *, run_number: int) -> str:
        base = channel.label or channel.channel_id.value
        return f"#{run_number} {base}"

    # -- testing affordances -------------------------------------------------

    @property
    def active_run(self) -> _TraceRun | None:
        return self._active

    @property
    def history(self) -> list[_TraceRun]:
        return list(self._history)


def _measured_channels(setup: Setup) -> list[ChannelConfig]:
    """Channels we plot a curve for. Currently the VAR1 channel only.

    Expand to include companion measurement channels once FlexDriver issues
    multi-channel ``MM`` commands.
    """
    return [c for c in setup.channels if c.function is ChannelFunction.VAR1]


__all__ = ["PlotView"]
