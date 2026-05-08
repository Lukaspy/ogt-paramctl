"""Integration tests for the QoL toolbar additions: log-Y and cursor readout."""
from __future__ import annotations

import pytest

from paramctl.driver import MockDriver
from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepMeasurement,
    SweepRange,
)
from paramctl.ui.main_window import MainWindow


def _setup() -> Setup:
    return Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=1e-3,
                label="Drain",
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=1.0, points=5)
        ),
    )


@pytest.fixture
def driver():
    drv = MockDriver(inter_sample_delay_s=0.0)
    drv.connect()
    yield drv
    drv.disconnect()


def test_log_y_checkbox_toggles_plot(qtbot, driver) -> None:
    """``mouseClick`` on a QCheckBox is unreliable under offscreen Qt.
    Use ``click()`` which toggles + emits ``toggled`` deterministically.
    """
    win = MainWindow(driver, _setup())
    qtbot.addWidget(win)
    assert win._plot.is_log_y() is False
    win._log_y_check.click()
    assert win._plot.is_log_y() is True
    win._log_y_check.click()
    assert win._plot.is_log_y() is False


def test_cursor_label_updates_from_plot_signal(qtbot, driver) -> None:
    win = MainWindow(driver, _setup())
    qtbot.addWidget(win)
    win._plot.cursor_changed.emit("X: 1.5 V    Y: 200 uA")
    assert win._cursor_label.text() == "X: 1.5 V    Y: 200 uA"


def test_cursor_label_clears_when_signal_is_empty(qtbot, driver) -> None:
    win = MainWindow(driver, _setup())
    qtbot.addWidget(win)
    win._plot.cursor_changed.emit("X: 1 V    Y: 1 mA")
    win._plot.cursor_changed.emit("")
    assert win._cursor_label.text() == ""
