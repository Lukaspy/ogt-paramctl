"""Multi-trace measurement plot built on pyqtgraph.

Each completed run leaves its curves on the plot, recoloured and dimmed so
the active trace is visually distinct. Useful workflow: tweak a parameter,
run, compare against the previous trace; older traces stay visible until
you call ``clear_history()``.

Quality-of-life features in this revision:
    - Axis labels reflect the active VAR1 channel's label and source mode.
    - ``set_log_y`` toggles a logarithmic Y axis (essential for diode IV).
    - Mouse hover emits a formatted ``cursor_changed`` signal carrying the
      current X/Y position so the main window can show it in the status bar.
"""
from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from ...models.channel import ChannelConfig, ChannelFunction, ChannelId, ChannelMode
from ...models.results import Sample
from ...models.setup import Setup
from ...util.units import format_si

logger = logging.getLogger(__name__)


_ACTIVE_COLOUR = QColor("yellow")
_ACTIVE_LINE_WIDTH = 2
_COMPLIANCE_COLOUR = QColor(255, 60, 60)  # bright red — drowns out yellow

_HISTORY_HUES: tuple[QColor, ...] = (
    QColor(255, 140, 0),
    QColor(0, 200, 255),
    QColor(255, 80, 200),
    QColor(120, 255, 80),
    QColor(180, 130, 255),
    QColor(255, 220, 80),
)
_HISTORY_LINE_WIDTH = 1
_HISTORY_ALPHA_MIN = 60
_HISTORY_ALPHA_MAX = 200


@dataclass
class _TraceRun:
    """One completed-or-active run's curves on the plot.

    Stores the original ``Sample`` objects so CSV export and any future
    analysis can reach back to timestamps, compliance flags, and the
    per-channel reading map without depending on the plot's own derived
    arrays.
    """

    setup: Setup
    samples: list[Sample] = field(default_factory=list)
    curves: dict[ChannelId, pg.PlotDataItem] = field(default_factory=dict)

    def channel_series(
        self, channel_id: ChannelId
    ) -> tuple[list[float], list[float], list[bool]]:
        xs: list[float] = []
        ys: list[float] = []
        hits: list[bool] = []
        for s in self.samples:
            if s.var1_value is None:
                continue
            value = s.readings.get(channel_id)
            if value is None:
                continue
            xs.append(s.var1_value)
            ys.append(value)
            hits.append(s.compliance_hit)
        return xs, ys, hits


class PlotView(QWidget):
    """Plots ``Sample`` data live with multi-run history.

    Signals:
        cursor_changed(str): A pre-formatted "X = …, Y = …" string emitted
            when the mouse moves over the plot area. Empty string when the
            mouse leaves. Connect to a status-bar label.
    """

    cursor_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plot = pg.PlotWidget()
        self._plot.setBackground("k")
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._legend = self._plot.addLegend()
        self._plot.setLabel("bottom", "VAR1")
        self._plot.setLabel("left", "Reading")

        self._cursor_line = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen("#888", width=1, style=Qt.PenStyle.DashLine),
        )
        self._cursor_line.setVisible(False)
        self._plot.addItem(self._cursor_line, ignoreBounds=True)
        self._plot.scene().sigMouseMoved.connect(self._on_mouse_moved)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._plot)

        self._history: list[_TraceRun] = []
        self._active: _TraceRun | None = None
        self._run_counter = 0
        self._x_unit: str = ""
        self._y_unit: str = ""
        self._log_y = False

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
                symbolSize=5,
                symbolBrush=_ACTIVE_COLOUR,
                symbolPen=_ACTIVE_COLOUR,
            )
            run.curves[channel.channel_id] = curve

        self._active = run

    def add_sample(self, sample: Sample) -> None:
        if self._active is None or sample.var1_value is None:
            return
        self._active.samples.append(sample)
        for channel_id, curve in self._active.curves.items():
            xs, ys, hits = self._active.channel_series(channel_id)
            if not xs:
                continue
            brushes = [
                pg.mkBrush(_COMPLIANCE_COLOUR if hit else _ACTIVE_COLOUR)
                for hit in hits
            ]
            symbol_pens = [
                pg.mkPen(_COMPLIANCE_COLOUR if hit else _ACTIVE_COLOUR) for hit in hits
            ]
            curve.setData(xs, ys, symbolBrush=brushes, symbolPen=symbol_pens)

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

    # -- toggles -------------------------------------------------------------

    def set_log_y(self, enabled: bool) -> None:
        """Toggle a base-10 logarithmic Y axis. Negative-Y points become NaN."""
        self._log_y = bool(enabled)
        self._plot.setLogMode(y=self._log_y)

    def is_log_y(self) -> bool:
        return self._log_y

    # -- styling -------------------------------------------------------------

    def _configure_axes(self, setup: Setup) -> None:
        var1 = next(c for c in setup.channels if c.function is ChannelFunction.VAR1)
        name = var1.label or var1.channel_id.value
        if var1.mode is ChannelMode.V_SOURCE:
            self._x_unit = "V"
            self._y_unit = "A"
            self._plot.setLabel("bottom", f"{name} voltage", units="V")
            self._plot.setLabel("left", f"{name} current", units="A")
        else:
            self._x_unit = "A"
            self._y_unit = "V"
            self._plot.setLabel("bottom", f"{name} current", units="A")
            self._plot.setLabel("left", f"{name} voltage", units="V")

    def _recolour_history(self) -> None:
        if not self._history:
            return
        n = len(self._history)
        for index, run in enumerate(self._history):
            age_factor = (index + 1) / n
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

    # -- cursor --------------------------------------------------------------

    def _on_mouse_moved(self, pos: object) -> None:
        # ``pos`` is a QPointF in scene coordinates.
        from PyQt6.QtCore import QPointF

        if not isinstance(pos, QPointF):
            return
        item = self._plot.plotItem
        if not item.sceneBoundingRect().contains(pos):
            self._cursor_line.setVisible(False)
            self.cursor_changed.emit("")
            return

        view_pos = item.vb.mapSceneToView(pos)
        x = view_pos.x()
        y = view_pos.y()

        # If log-Y is on, the displayed Y is log10(value); raise back to linear.
        if self.is_log_y():
            with contextlib.suppress(OverflowError, ValueError):
                y = pow(10.0, y)

        self._cursor_line.setPos(x)
        self._cursor_line.setVisible(True)

        x_str = format_si(x, unit=self._x_unit) if self._x_unit else format_si(x)
        y_str = format_si(y, unit=self._y_unit) if self._y_unit else format_si(y)
        self.cursor_changed.emit(f"X: {x_str}    Y: {y_str}")

    # -- testing affordances -------------------------------------------------

    @property
    def active_run(self) -> _TraceRun | None:
        return self._active

    @property
    def history(self) -> list[_TraceRun]:
        return list(self._history)

    @property
    def x_unit(self) -> str:
        return self._x_unit

    @property
    def y_unit(self) -> str:
        return self._y_unit


def _measured_channels(setup: Setup) -> list[ChannelConfig]:
    """Channels we plot a curve for. Currently the VAR1 channel only."""
    return [c for c in setup.channels if c.function is ChannelFunction.VAR1]


__all__ = ["PlotView"]
