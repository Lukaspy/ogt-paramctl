"""Integration tests for setup save/load and trace export from MainWindow."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt

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
from paramctl.persistence import load_setup, read_run_csv, save_setup
from paramctl.ui.main_window import MainWindow


def _setup(points: int = 5) -> Setup:
    return Setup(
        name="ID-VDS smoke",
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10e-3,
                label="Drain",
            ),
            ChannelConfig(
                channel_id=ChannelId.SMU2,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.CONST,
                source_value=1.5,
                compliance=1e-3,
                label="Gate",
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=1.0, points=points)
        ),
    )


@pytest.fixture
def driver():
    drv = MockDriver(inter_sample_delay_s=0.0)
    drv.connect()
    yield drv
    drv.disconnect()


def _wait_for_thread_cleanup(qtbot, win: MainWindow) -> None:
    qtbot.waitUntil(lambda: win._thread is None, timeout=3000)


def test_save_setup_then_load_into_fresh_window(qtbot, driver, tmp_path) -> None:
    win = MainWindow(driver, _setup())
    qtbot.addWidget(win)

    target = tmp_path / "saved.yaml"
    save_setup(target, win._editor.current_setup())

    win2 = MainWindow(driver, _setup(points=11))
    qtbot.addWidget(win2)
    win2._editor.populate_from(load_setup(target))

    assert win2._editor.current_setup() == win._editor.current_setup()


def test_export_trace_button_disabled_until_run_completes(qtbot, driver) -> None:
    win = MainWindow(driver, _setup(points=5))
    qtbot.addWidget(win)
    assert not win._export_btn.isEnabled()

    with qtbot.waitSignal(win.sweep_completed, timeout=5000):
        qtbot.mouseClick(win._run_btn, Qt.MouseButton.LeftButton)
    _wait_for_thread_cleanup(qtbot, win)

    assert win._export_btn.isEnabled()


def test_clear_traces_disables_export_button(qtbot, driver) -> None:
    win = MainWindow(driver, _setup(points=5))
    qtbot.addWidget(win)
    with qtbot.waitSignal(win.sweep_completed, timeout=5000):
        qtbot.mouseClick(win._run_btn, Qt.MouseButton.LeftButton)
    _wait_for_thread_cleanup(qtbot, win)
    assert win._export_btn.isEnabled()

    qtbot.mouseClick(win._clear_btn, Qt.MouseButton.LeftButton)
    assert not win._export_btn.isEnabled()


def test_active_run_csv_round_trip(qtbot, driver, tmp_path) -> None:
    """The active run can be exported and re-read with the same setup + samples."""
    from paramctl.persistence import write_run_csv

    win = MainWindow(driver, _setup(points=11))
    qtbot.addWidget(win)
    with qtbot.waitSignal(win.sweep_completed, timeout=5000):
        qtbot.mouseClick(win._run_btn, Qt.MouseButton.LeftButton)
    _wait_for_thread_cleanup(qtbot, win)

    active = win._plot.active_run
    assert active is not None
    target = tmp_path / "trace.csv"
    write_run_csv(target, active.setup, active.samples)

    setup, samples = read_run_csv(target)
    assert setup == active.setup
    assert len(samples) == 11
