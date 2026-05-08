"""Orchestrates a measurement run on top of an ``AnalyzerDriver``.

The engine is intentionally Qt-free: it is a generator function that emits
``SweepEvent`` instances. The ui layer wraps it in a ``QThread`` worker that
forwards each event into a Qt signal. Tests drive it directly with a
``MockDriver`` and a plain ``threading.Event`` for cancellation.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Iterator

from ..driver.base import AnalyzerDriver
from ..models.setup import Setup
from .events import (
    SampleReady,
    SweepCompleted,
    SweepEvent,
    SweepFailed,
    SweepStarted,
)

logger = logging.getLogger(__name__)


def run_sweep(
    driver: AnalyzerDriver,
    setup: Setup,
    *,
    abort_event: threading.Event | None = None,
) -> Iterator[SweepEvent]:
    """Run a single measurement and stream its events.

    Args:
        driver: A connected ``AnalyzerDriver`` (real or mock). The engine
            does not call ``connect()``; the caller is responsible for the
            connection lifecycle so the same driver can be reused across
            multiple runs.
        setup: The validated ``Setup`` describing the measurement.
        abort_event: Optional ``threading.Event`` the caller can set from
            another thread to cancel the run. The engine forwards the
            cancellation to ``driver.abort()`` and closes the driver's
            iterator. If omitted, an internal event is used (the caller
            cannot then cancel — useful for synchronous test runs).

    Yields:
        Events in this order:
            ``SweepStarted`` -> ``SampleReady`` * N -> terminal event.
        Where the terminal event is exactly one of ``SweepCompleted`` or
        ``SweepFailed``.

    The function never raises out of itself: driver exceptions are
    captured and surfaced as ``SweepFailed``. ``KeyboardInterrupt`` and
    ``SystemExit`` propagate.
    """
    abort = abort_event if abort_event is not None else threading.Event()

    yield SweepStarted(setup=setup)

    sample_count = 0
    aborted_in_loop = False
    measure_iter = driver.measure(setup)

    try:
        for sample in measure_iter:
            sample_count += 1
            yield SampleReady(sample=sample)
            if abort.is_set():
                logger.info("run_sweep: abort requested after %d samples", sample_count)
                driver.abort()
                _close_iterator(measure_iter)
                aborted_in_loop = True
                break
    except (KeyboardInterrupt, SystemExit):
        _close_iterator(measure_iter)
        raise
    except Exception as exc:
        logger.exception("run_sweep: driver raised after %d samples", sample_count)
        _close_iterator(measure_iter)
        yield SweepFailed(exception=exc, sample_count=sample_count)
        return

    # Iterator exhausted. The run was aborted iff either:
    #   (a) we broke out of the loop on the abort flag, or
    #   (b) the driver itself self-terminated because abort was set
    #       (e.g. FlexDriver._wait_for_data returns early when its abort
    #       flag is observed, leaving the iterator with no more samples).
    aborted = aborted_in_loop or abort.is_set()
    yield SweepCompleted(aborted=aborted, sample_count=sample_count)


def _close_iterator(it: Iterator[object]) -> None:
    """Best-effort ``close()`` on a possibly-generator iterator."""
    closer = getattr(it, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:
            logger.exception("run_sweep: error during iterator close")


__all__ = ["run_sweep"]
