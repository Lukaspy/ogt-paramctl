"""Qt worker that runs a measurement on a background thread.

The engine layer is Qt-free; this module is the bridge. ``SweepWorker``
owns no Qt event loop of its own — it is meant to be moved onto a
``QThread`` whose ``started`` signal triggers ``run()``. Each engine
event becomes a Qt signal so the main thread can update widgets without
touching the worker thread.

Threading rules (CLAUDE.md §100):
    - The driver call lives on this worker.
    - VISA never runs on the Qt main thread.
    - Cancellation is signalled via a ``threading.Event`` shared with the
      caller; the caller also calls ``driver.abort()`` directly so any
      blocking transport read is interrupted promptly.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from ..driver.base import AnalyzerDriver
from ..engine import (
    SampleReady,
    SweepCompleted,
    SweepFailed,
    SweepStarted,
    run_sweep,
)
from ..models.setup import Setup

logger = logging.getLogger(__name__)


class SweepWorker(QObject):
    """Runs ``run_sweep`` on its containing thread and re-emits as Qt signals.

    Signals:
        started(Setup): emitted once when the run begins.
        sample(Sample): emitted for each ``SampleReady`` event.
        completed(int, bool): sample_count, aborted; emitted at natural or
            cancelled end.
        failed(object, int): exception, sample_count; emitted if the driver
            raises mid-run.
        finished(): emitted unconditionally after either completed or failed,
            so the caller can quit the QThread without listening to two
            terminal signals.
    """

    started = pyqtSignal(object)        # Setup
    sample = pyqtSignal(object)         # Sample
    completed = pyqtSignal(int, bool)
    failed = pyqtSignal(object, int)
    finished = pyqtSignal()

    def __init__(
        self,
        driver: AnalyzerDriver,
        setup: Setup,
        abort_event: threading.Event,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._driver = driver
        self._setup = setup
        self._abort_event = abort_event

    def run(self) -> None:
        """Entry point. Connect a ``QThread.started`` signal to this slot."""
        try:
            for event in run_sweep(
                self._driver, self._setup, abort_event=self._abort_event
            ):
                if isinstance(event, SweepStarted):
                    self.started.emit(event.setup)
                elif isinstance(event, SampleReady):
                    self.sample.emit(event.sample)
                elif isinstance(event, SweepCompleted):
                    self.completed.emit(event.sample_count, event.aborted)
                elif isinstance(event, SweepFailed):
                    self.failed.emit(event.exception, event.sample_count)
        except BaseException as exc:
            # run_sweep itself is supposed to capture driver exceptions, so
            # reaching here means something more fundamental went wrong (e.g.
            # KeyboardInterrupt; or a bug in the engine). Surface it as failed.
            logger.exception("SweepWorker: unexpected exception")
            self.failed.emit(exc, 0)
        finally:
            self.finished.emit()


# Convenience reference so callers do not need to depend on internal types.
SweepWorkerSignals: tuple[Any, ...] = (
    SweepWorker.started,
    SweepWorker.sample,
    SweepWorker.completed,
    SweepWorker.failed,
    SweepWorker.finished,
)


__all__ = ["SweepWorker"]
