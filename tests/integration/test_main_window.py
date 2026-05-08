"""Integration tests for the editor + multi-trace MainWindow."""
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
from paramctl.ui.main_window import MainWindow


def _setup(points: int = 11) -> Setup:
    return Setup(
        name="UI smoke",
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=1e-3,
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
def fast_driver():
    drv = MockDriver(inter_sample_delay_s=0.0)
    drv.connect()
    yield drv
    drv.disconnect()


@pytest.fixture
def slow_driver():
    drv = MockDriver(inter_sample_delay_s=0.05)
    drv.connect()
    yield drv
    drv.disconnect()


def _wait_for_thread_cleanup(qtbot, win: MainWindow, timeout_ms: int = 3000) -> None:
    qtbot.waitUntil(lambda: win._thread is None, timeout=timeout_ms)


def test_run_button_drives_sweep_to_completion(qtbot, fast_driver) -> None:
    win = MainWindow(fast_driver, _setup(points=11))
    qtbot.addWidget(win)

    with qtbot.waitSignal(win.sweep_completed, timeout=5000) as blocker:
        qtbot.mouseClick(win._run_btn, Qt.MouseButton.LeftButton)

    count, aborted = blocker.args
    assert count == 11
    assert aborted is False
    _wait_for_thread_cleanup(qtbot, win)


def test_run_button_disables_during_sweep(qtbot, slow_driver) -> None:
    win = MainWindow(slow_driver, _setup(points=20))
    qtbot.addWidget(win)

    with qtbot.waitSignal(win.sweep_completed, timeout=5000):
        qtbot.mouseClick(win._run_btn, Qt.MouseButton.LeftButton)
        qtbot.waitUntil(lambda: not win._run_btn.isEnabled(), timeout=1000)
        assert win._stop_btn.isEnabled()

    _wait_for_thread_cleanup(qtbot, win)
    assert win._run_btn.isEnabled()
    assert not win._stop_btn.isEnabled()


def test_stop_button_aborts_sweep(qtbot, slow_driver) -> None:
    win = MainWindow(slow_driver, _setup(points=200))
    qtbot.addWidget(win)

    with qtbot.waitSignal(win.sweep_completed, timeout=5000) as blocker:
        qtbot.mouseClick(win._run_btn, Qt.MouseButton.LeftButton)
        qtbot.wait(150)
        qtbot.mouseClick(win._stop_btn, Qt.MouseButton.LeftButton)

    count, aborted = blocker.args
    assert aborted is True
    assert 0 < count < 200
    _wait_for_thread_cleanup(qtbot, win)


def test_plot_accumulates_samples_in_active_run(qtbot, fast_driver) -> None:
    win = MainWindow(fast_driver, _setup(points=11))
    qtbot.addWidget(win)

    with qtbot.waitSignal(win.sweep_completed, timeout=5000):
        qtbot.mouseClick(win._run_btn, Qt.MouseButton.LeftButton)

    active = win._plot.active_run
    assert active is not None
    assert len(active.x) == 11
    _wait_for_thread_cleanup(qtbot, win)


def test_subsequent_runs_demote_previous_to_history(qtbot, fast_driver) -> None:
    win = MainWindow(fast_driver, _setup(points=7))
    qtbot.addWidget(win)

    with qtbot.waitSignal(win.sweep_completed, timeout=5000):
        qtbot.mouseClick(win._run_btn, Qt.MouseButton.LeftButton)
    _wait_for_thread_cleanup(qtbot, win)

    with qtbot.waitSignal(win.sweep_completed, timeout=5000):
        qtbot.mouseClick(win._run_btn, Qt.MouseButton.LeftButton)
    _wait_for_thread_cleanup(qtbot, win)

    assert len(win._plot.history) == 1
    assert win._plot.active_run is not None


def test_clear_traces_removes_history(qtbot, fast_driver) -> None:
    win = MainWindow(fast_driver, _setup(points=5))
    qtbot.addWidget(win)

    for _ in range(2):
        with qtbot.waitSignal(win.sweep_completed, timeout=5000):
            qtbot.mouseClick(win._run_btn, Qt.MouseButton.LeftButton)
        _wait_for_thread_cleanup(qtbot, win)

    qtbot.mouseClick(win._clear_btn, Qt.MouseButton.LeftButton)
    assert win._plot.active_run is None
    assert win._plot.history == []


def test_invalid_setup_surfaces_in_status_bar(qtbot, fast_driver) -> None:
    win = MainWindow(fast_driver, _setup(points=11))
    qtbot.addWidget(win)

    # Disable every channel via the editor; clicking Run should show an error
    # rather than start a thread.
    for row in win._editor._channels._rows.values():
        row.enable_check.setChecked(False)

    qtbot.mouseClick(win._run_btn, Qt.MouseButton.LeftButton)
    qtbot.wait(50)

    assert win._thread is None
    assert "invalid" in win._status_bar.currentMessage().lower()
