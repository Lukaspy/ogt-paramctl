"""Synthetic driver that satisfies ``AnalyzerDriver`` without any I/O.

``MockDriver`` is the backbone of mock-first development. The whole stack —
engine, persistence, ui — must work end-to-end against this driver so that
contributors do not need a real 4155/4156 on the bench to make progress.

The synthesis math lives in ``paramctl.driver.synth``; this module just
sequences the lifecycle and exposes the abort/state surface.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator

from ..models.measurement import SweepMeasurement
from ..models.results import Sample
from ..models.setup import Setup
from .base import AnalyzerDriver, NotConnectedError
from .synth import sweep_points, synth_readings

logger = logging.getLogger(__name__)


class MockDriver(AnalyzerDriver):
    """In-memory ``AnalyzerDriver`` returning a fixed IDN and synthesised samples.

    Attributes:
        DEFAULT_IDN: Default IDN response when no override is supplied.
    """

    DEFAULT_IDN: str = "Agilent Technologies,4155B,MOCK-0000000,REV99.99-MOCK"

    def __init__(
        self,
        idn: str = DEFAULT_IDN,
        *,
        inter_sample_delay_s: float = 0.0,
    ) -> None:
        """Construct a mock driver.

        Args:
            idn: IDN string returned from ``idn()``.
            inter_sample_delay_s: Synthetic per-sample wall-clock delay.
                Defaults to zero so unit tests run instantly. The example
                script bumps it to a few milliseconds to make the live-plot
                experience feel like real hardware.
        """
        self._idn = idn
        self._inter_sample_delay_s = max(0.0, inter_sample_delay_s)
        self._connected = False
        self._reset_count = 0
        self._abort_event = threading.Event()

    def connect(self) -> None:
        logger.debug("MockDriver.connect()")
        self._connected = True

    def disconnect(self) -> None:
        if self._connected:
            logger.debug("MockDriver.disconnect()")
        self._connected = False
        self._abort_event.set()  # wake any in-flight measure() generator

    def idn(self) -> str:
        if not self._connected:
            raise NotConnectedError("MockDriver is not connected")
        return self._idn

    def reset(self) -> None:
        if not self._connected:
            raise NotConnectedError("MockDriver is not connected")
        self._reset_count += 1
        self._abort_event.clear()
        logger.debug("MockDriver.reset() (count=%d)", self._reset_count)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def reset_count(self) -> int:
        """Number of times ``reset()`` has been called (test affordance)."""
        return self._reset_count

    def abort(self) -> None:
        """Set the abort flag; the active ``measure()`` generator exits promptly."""
        self._abort_event.set()
        logger.debug("MockDriver.abort()")

    def measure(self, setup: Setup) -> Iterator[Sample]:
        if not self._connected:
            raise NotConnectedError("MockDriver is not connected")
        if not isinstance(setup.measurement, SweepMeasurement):
            raise NotImplementedError(
                f"MockDriver currently only models sweep measurements; "
                f"received {type(setup.measurement).__name__}."
            )
        return self._sweep_iterator(setup, setup.measurement)

    def _sweep_iterator(
        self, setup: Setup, sweep: SweepMeasurement
    ) -> Iterator[Sample]:
        self._abort_event.clear()
        points = sweep_points(sweep.var1)
        start_time = time.monotonic()

        if sweep.hold_time > 0:
            self._interruptible_sleep(sweep.hold_time)

        try:
            for index, value in enumerate(points):
                if self._abort_event.is_set():
                    return

                if sweep.delay_time > 0:
                    self._interruptible_sleep(sweep.delay_time)

                readings, compliance_hit = synth_readings(setup, sweep, value)
                sample = Sample(
                    index=index,
                    var1_value=value,
                    readings=readings,
                    timestamp=time.monotonic() - start_time,
                    compliance_hit=compliance_hit,
                )

                if self._inter_sample_delay_s > 0:
                    self._interruptible_sleep(self._inter_sample_delay_s)

                if self._abort_event.is_set():
                    return

                yield sample
        finally:
            logger.debug("MockDriver._sweep_iterator exit")

    def _interruptible_sleep(self, duration_s: float, *, poll_interval_s: float = 0.05) -> None:
        """Sleep up to ``duration_s`` but wake immediately on abort.

        Keeps mock cancellation latency well under CLAUDE.md's 1 s budget
        even when the configured inter-sample delay is large.
        """
        if duration_s <= 0:
            return
        deadline = time.monotonic() + duration_s
        while not self._abort_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(poll_interval_s, remaining))
