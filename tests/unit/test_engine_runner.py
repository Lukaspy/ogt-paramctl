"""Tests for ``paramctl.engine.run_sweep`` orchestration."""
from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import pytest

from paramctl.driver import AnalyzerDriver, MockDriver
from paramctl.engine import (
    SampleReady,
    SweepCompleted,
    SweepFailed,
    SweepStarted,
    run_sweep,
)
from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Sample,
    Setup,
    SweepMeasurement,
    SweepRange,
)


def _basic_setup(points: int = 11) -> Setup:
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
                source_value=1.5,
                compliance=1e-3,
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=1.0, points=points)
        ),
    )


def _drain(it: Iterator[object]) -> list[object]:
    return list(it)


def test_run_sweep_emits_started_samples_and_completed() -> None:
    drv = MockDriver()
    drv.connect()
    events = _drain(run_sweep(drv, _basic_setup(points=5)))

    assert isinstance(events[0], SweepStarted)
    assert events[0].setup.measurement.var1.points == 5  # type: ignore[union-attr]

    samples = [e for e in events if isinstance(e, SampleReady)]
    assert len(samples) == 5

    terminal = events[-1]
    assert isinstance(terminal, SweepCompleted)
    assert terminal.aborted is False
    assert terminal.sample_count == 5


def test_run_sweep_passes_setup_to_started_event() -> None:
    drv = MockDriver()
    drv.connect()
    setup = _basic_setup(points=3)
    events = _drain(run_sweep(drv, setup))
    started = events[0]
    assert isinstance(started, SweepStarted)
    assert started.setup is setup


def test_abort_event_terminates_run_with_aborted_completion() -> None:
    drv = MockDriver(inter_sample_delay_s=0.05)
    drv.connect()
    abort = threading.Event()

    events: list[object] = []
    setup = _basic_setup(points=200)

    def consumer() -> None:
        for e in run_sweep(drv, setup, abort_event=abort):
            events.append(e)

    t = threading.Thread(target=consumer)
    t.start()
    time.sleep(0.15)
    abort.set()
    t.join(timeout=2.0)

    assert not t.is_alive()
    terminal = events[-1]
    assert isinstance(terminal, SweepCompleted)
    assert terminal.aborted is True
    assert 0 < terminal.sample_count < 200


def test_driver_exception_surfaces_as_sweep_failed() -> None:
    class BrokenDriver(AnalyzerDriver):
        def connect(self) -> None: ...
        def disconnect(self) -> None: ...
        def idn(self) -> str:
            return "broken"
        def reset(self) -> None: ...
        @property
        def is_connected(self) -> bool:
            return True
        def abort(self) -> None: ...
        def measure(self, setup: Setup) -> Iterator[Sample]:
            yield Sample(index=0, var1_value=0.0, readings={})
            raise RuntimeError("instrument exploded")

    events = _drain(run_sweep(BrokenDriver(), _basic_setup()))

    assert isinstance(events[0], SweepStarted)
    assert isinstance(events[1], SampleReady)
    terminal = events[-1]
    assert isinstance(terminal, SweepFailed)
    assert isinstance(terminal.exception, RuntimeError)
    assert "exploded" in str(terminal.exception)
    assert terminal.sample_count == 1


def test_keyboard_interrupt_propagates() -> None:
    class InterruptingDriver(AnalyzerDriver):
        def connect(self) -> None: ...
        def disconnect(self) -> None: ...
        def idn(self) -> str:
            return "ki"
        def reset(self) -> None: ...
        @property
        def is_connected(self) -> bool:
            return True
        def abort(self) -> None: ...
        def measure(self, setup: Setup) -> Iterator[Sample]:
            yield Sample(index=0, var1_value=0.0, readings={})
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        for _ in run_sweep(InterruptingDriver(), _basic_setup()):
            pass


def test_no_abort_event_runs_to_completion() -> None:
    drv = MockDriver()
    drv.connect()
    events = _drain(run_sweep(drv, _basic_setup(points=4)))
    terminal = events[-1]
    assert isinstance(terminal, SweepCompleted)
    assert terminal.aborted is False


def test_completed_sample_count_matches_sample_events() -> None:
    drv = MockDriver()
    drv.connect()
    events = _drain(run_sweep(drv, _basic_setup(points=17)))
    sample_events = [e for e in events if isinstance(e, SampleReady)]
    terminal = events[-1]
    assert isinstance(terminal, SweepCompleted)
    assert terminal.sample_count == len(sample_events)
