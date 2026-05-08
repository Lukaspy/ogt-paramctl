"""Tests for ``SweepWorker`` — the QThread-friendly bridge over ``run_sweep``.

These run the worker on the main thread (no QThread spin-up) since the
worker contains no Qt event-loop logic of its own — it just emits signals
as it iterates the engine. That keeps the tests fast and deterministic.
"""
from __future__ import annotations

import threading

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
from paramctl.ui.workers import SweepWorker


def _basic_setup(points: int = 7) -> Setup:
    return Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=1e-3,
            ),
            ChannelConfig(
                channel_id=ChannelId.SMU2,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.CONST,
                source_value=1.0,
                compliance=1e-3,
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=1.0, points=points)
        ),
    )


def test_worker_emits_started_samples_completed(qtbot) -> None:
    drv = MockDriver()
    drv.connect()

    worker = SweepWorker(drv, _basic_setup(points=5), threading.Event())
    samples = []
    worker.sample.connect(samples.append)

    started_count = 0
    def _on_started(setup):
        nonlocal started_count
        started_count += 1
    worker.started.connect(_on_started)

    with (
        qtbot.waitSignal(worker.completed, timeout=2000) as blocker,
        qtbot.waitSignal(worker.finished, timeout=2000),
    ):
        worker.run()

    sample_count, aborted = blocker.args
    assert sample_count == 5
    assert aborted is False
    assert started_count == 1
    assert len(samples) == 5


def test_worker_aborts_when_event_set(qtbot) -> None:
    drv = MockDriver(inter_sample_delay_s=0.05)
    drv.connect()
    abort = threading.Event()
    worker = SweepWorker(drv, _basic_setup(points=200), abort)

    samples_seen: list[object] = []
    worker.sample.connect(samples_seen.append)

    # Fire abort once a few samples have arrived.
    def _abort_after_a_few(_sample) -> None:
        if len(samples_seen) >= 3 and not abort.is_set():
            abort.set()
            drv.abort()
    worker.sample.connect(_abort_after_a_few)

    with qtbot.waitSignal(worker.completed, timeout=5000) as blocker:
        worker.run()

    sample_count, aborted = blocker.args
    assert aborted is True
    assert 0 < sample_count < 200


def test_worker_failed_signal_on_driver_exception(qtbot) -> None:
    from collections.abc import Iterator

    from paramctl.driver.base import AnalyzerDriver
    from paramctl.models.results import Sample

    class BoomDriver(AnalyzerDriver):
        def connect(self) -> None: ...
        def disconnect(self) -> None: ...
        def idn(self) -> str:
            return "boom"
        def reset(self) -> None: ...
        @property
        def is_connected(self) -> bool:
            return True
        def abort(self) -> None: ...
        def measure(self, setup: Setup) -> Iterator[Sample]:
            yield Sample(index=0, var1_value=0.0, readings={})
            raise RuntimeError("kaboom")

    worker = SweepWorker(BoomDriver(), _basic_setup(), threading.Event())

    with qtbot.waitSignal(worker.failed, timeout=2000) as blocker:
        worker.run()

    exc, count = blocker.args
    assert isinstance(exc, RuntimeError)
    assert "kaboom" in str(exc)
    assert count == 1


def test_worker_finished_always_emits(qtbot) -> None:
    """``finished`` fires whether the run completes or fails — required by
    MainWindow which uses it to terminate the QThread regardless of outcome."""
    drv = MockDriver()
    drv.connect()
    worker = SweepWorker(drv, _basic_setup(points=3), threading.Event())

    with qtbot.waitSignal(worker.finished, timeout=2000):
        worker.run()
