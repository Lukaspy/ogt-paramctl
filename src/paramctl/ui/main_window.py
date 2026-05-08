"""Top-level window for the M0 thin slice.

Renders a fixed setup (passed in by the launcher), provides Run / Stop
buttons, and shows samples on a live ``PlotView`` as they arrive. The
window owns the worker QThread lifecycle but never touches the driver
itself — that responsibility lives on the worker thread.

This is intentionally minimal: no channel/sweep editor, no setup
load/save, no menu bar. Those land in subsequent UI commits once the
threading + plotting + abort flow is validated end-to-end.
"""
from __future__ import annotations

import logging
import threading

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..driver.base import AnalyzerDriver
from ..models.results import Sample
from ..models.setup import Setup
from .widgets import PlotView
from .workers import SweepWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Run / Stop a single sweep against the supplied driver and plot it."""

    # Public signals for tests and external listeners.
    sweep_completed = pyqtSignal(int, bool)
    sweep_failed = pyqtSignal(object, int)

    def __init__(
        self,
        driver: AnalyzerDriver,
        setup: Setup,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._driver = driver
        self._setup = setup

        self._thread: QThread | None = None
        self._worker: SweepWorker | None = None
        self._abort_event: threading.Event | None = None

        self.setWindowTitle(f"paramctl — {setup.name or 'untitled setup'}")
        self._build_ui()
        self._wire_buttons()

    # --- UI assembly --------------------------------------------------------

    def _build_ui(self) -> None:
        self._run_btn = QPushButton("Run")
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._idn_label = QLabel(f"Driver: {type(self._driver).__name__}")

        controls = QHBoxLayout()
        controls.addWidget(self._run_btn)
        controls.addWidget(self._stop_btn)
        controls.addStretch()
        controls.addWidget(self._idn_label)

        self._plot = PlotView()
        self._plot.configure_for(self._setup)

        layout = QVBoxLayout()
        layout.addLayout(controls)
        layout.addWidget(self._plot, stretch=1)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

    def _wire_buttons(self) -> None:
        self._run_btn.clicked.connect(self._on_run)
        self._stop_btn.clicked.connect(self._on_stop)

    # --- run / stop ---------------------------------------------------------

    def _on_run(self) -> None:
        if self._thread is not None:
            logger.warning("MainWindow: run requested while a sweep is already active")
            return

        self._plot.clear_curves()
        self._abort_event = threading.Event()
        worker = SweepWorker(self._driver, self._setup, self._abort_event)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.started.connect(self._on_started)
        worker.sample.connect(self._on_sample)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._cleanup_thread)

        self._worker = worker
        self._thread = thread
        self._run_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._status_bar.showMessage("Starting…")
        thread.start()

    def _on_stop(self) -> None:
        if self._abort_event is None:
            return
        self._status_bar.showMessage("Aborting…")
        self._abort_event.set()
        # Calling abort() from the GUI thread interrupts a blocking VISA read
        # inside the worker (CLAUDE.md §189: abort within ~1 second).
        self._driver.abort()

    # --- worker → ui slots --------------------------------------------------

    def _on_started(self, _setup: Setup) -> None:
        self._status_bar.showMessage("Running sweep…")

    def _on_sample(self, sample: Sample) -> None:
        self._plot.add_sample(sample)

    def _on_completed(self, sample_count: int, aborted: bool) -> None:
        verb = "Aborted" if aborted else "Done"
        self._status_bar.showMessage(f"{verb} ({sample_count} samples)", 5000)
        self.sweep_completed.emit(sample_count, aborted)

    def _on_failed(self, exc: BaseException, sample_count: int) -> None:
        self._status_bar.showMessage(
            f"Failed after {sample_count} samples: {exc}", 10000
        )
        self.sweep_failed.emit(exc, sample_count)

    # --- thread cleanup -----------------------------------------------------

    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self._abort_event = None
        self._run_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    # --- close handling -----------------------------------------------------

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        # Make sure no worker is left running on close.
        if self._abort_event is not None:
            self._abort_event.set()
        if self._thread is not None:
            try:
                self._driver.abort()
            except Exception:
                logger.exception("MainWindow: driver.abort() during close raised")
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(a0)


__all__ = ["MainWindow"]
