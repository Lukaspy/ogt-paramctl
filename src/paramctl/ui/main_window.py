"""Top-level window: setup editor on the left, multi-trace plot in the middle.

Run / Stop / Clear-traces sit on the toolbar at the top. Each click of Run
reads the current editor state into a fresh ``Setup``, validates it through
Pydantic (errors land in the status bar), and kicks off a new sweep on a
worker thread. Previous traces stay on the plot, recoloured, until the user
clicks Clear traces.
"""
from __future__ import annotations

import logging
import threading

from pydantic import ValidationError
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..driver.base import AnalyzerDriver
from ..models.results import Sample
from ..models.setup import Setup
from ..persistence import (
    SetupFileError,
    load_setup,
    save_setup,
    write_run_csv,
)
from .widgets import PlotView, SetupEditor
from .workers import SweepWorker

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Editor + plot + Run/Stop/Clear, wired to a single ``AnalyzerDriver``."""

    sweep_completed = pyqtSignal(int, bool)
    sweep_failed = pyqtSignal(object, int)

    def __init__(
        self,
        driver: AnalyzerDriver,
        initial_setup: Setup,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._driver = driver
        self._thread: QThread | None = None
        self._worker: SweepWorker | None = None
        self._abort_event: threading.Event | None = None

        self.setWindowTitle("paramctl")
        self._build_ui()
        self._editor.populate_from(initial_setup)
        self._wire_buttons()

    # --- UI assembly --------------------------------------------------------

    def _build_ui(self) -> None:
        self._open_btn = QPushButton("Open setup…")
        self._save_btn = QPushButton("Save setup…")
        self._run_btn = QPushButton("Run")
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._clear_btn = QPushButton("Clear traces")
        self._export_btn = QPushButton("Export trace…")
        self._export_btn.setEnabled(False)
        self._log_y_check = QCheckBox("Log Y")
        self._idn_label = QLabel(f"Driver: {type(self._driver).__name__}")

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._open_btn)
        toolbar.addWidget(self._save_btn)
        toolbar.addWidget(self._run_btn)
        toolbar.addWidget(self._stop_btn)
        toolbar.addWidget(self._clear_btn)
        toolbar.addWidget(self._export_btn)
        toolbar.addWidget(self._log_y_check)
        toolbar.addStretch()
        toolbar.addWidget(self._idn_label)

        self._editor = SetupEditor()
        editor_scroll = QScrollArea()
        editor_scroll.setWidget(self._editor)
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setMinimumWidth(420)

        self._plot = PlotView()

        splitter = QSplitter()
        splitter.addWidget(editor_scroll)
        splitter.addWidget(self._plot)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([460, 700])

        layout = QVBoxLayout()
        layout.addLayout(toolbar)
        layout.addWidget(splitter, stretch=1)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._cursor_label = QLabel("")
        self._status_bar.addPermanentWidget(self._cursor_label)

    def _wire_buttons(self) -> None:
        self._open_btn.clicked.connect(self._on_open_setup)
        self._save_btn.clicked.connect(self._on_save_setup)
        self._run_btn.clicked.connect(self._on_run)
        self._stop_btn.clicked.connect(self._on_stop)
        self._clear_btn.clicked.connect(self._on_clear)
        self._export_btn.clicked.connect(self._on_export_trace)
        self._log_y_check.toggled.connect(self._plot.set_log_y)
        self._plot.cursor_changed.connect(self._cursor_label.setText)

    # --- run / stop / clear -------------------------------------------------

    def _on_run(self) -> None:
        if self._thread is not None:
            logger.warning("MainWindow: run requested while a sweep is already active")
            return

        try:
            setup = self._editor.current_setup()
        except ValidationError as exc:
            first = exc.errors()[0]
            location = ".".join(str(p) for p in first.get("loc", ()))
            self._status_bar.showMessage(
                f"Setup invalid: {location}: {first.get('msg', exc)}", 10000
            )
            logger.warning("MainWindow: invalid setup: %s", exc)
            return

        self._plot.begin_run(setup)
        self._abort_event = threading.Event()
        worker = SweepWorker(self._driver, setup, self._abort_event)
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
        self._status_bar.showMessage(f"Starting {setup.name or 'untitled setup'}…")
        thread.start()

    def _on_stop(self) -> None:
        if self._abort_event is None:
            return
        self._status_bar.showMessage("Aborting…")
        self._abort_event.set()
        self._driver.abort()

    def _on_clear(self) -> None:
        if self._thread is not None:
            # Refuse to clear while a run is in flight: the active curve is
            # still being populated and removing it would leave the worker
            # writing into a deleted item.
            self._status_bar.showMessage(
                "Cannot clear traces while a sweep is running.", 5000
            )
            return
        self._plot.clear_history()
        self._export_btn.setEnabled(False)
        self._status_bar.showMessage("Traces cleared.", 3000)

    # --- persistence --------------------------------------------------------

    def _on_open_setup(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Open setup", "", "YAML setups (*.yaml *.yml);;All files (*)"
        )
        if not path:
            return
        try:
            setup = load_setup(path)
        except SetupFileError as exc:
            self._error_dialog("Could not open setup", str(exc))
            return
        self._editor.populate_from(setup)
        self._status_bar.showMessage(f"Loaded {path}", 5000)

    def _on_save_setup(self) -> None:
        try:
            setup = self._editor.current_setup()
        except ValidationError as exc:
            first = exc.errors()[0]
            location = ".".join(str(p) for p in first.get("loc", ()))
            self._status_bar.showMessage(
                f"Cannot save invalid setup: {location}: {first.get('msg', exc)}",
                10000,
            )
            return
        suggested = (setup.name or "setup").replace("/", "_") + ".yaml"
        path, _filter = QFileDialog.getSaveFileName(
            self, "Save setup", suggested, "YAML setups (*.yaml *.yml)"
        )
        if not path:
            return
        try:
            save_setup(path, setup)
        except OSError as exc:
            self._error_dialog("Could not save setup", str(exc))
            return
        self._status_bar.showMessage(f"Saved {path}", 5000)

    def _on_export_trace(self) -> None:
        active = self._plot.active_run
        if active is None or not active.samples:
            self._status_bar.showMessage("No active trace to export.", 5000)
            return
        suggested = (active.setup.name or "trace").replace("/", "_") + ".csv"
        path, _filter = QFileDialog.getSaveFileName(
            self, "Export trace", suggested, "CSV traces (*.csv)"
        )
        if not path:
            return
        try:
            write_run_csv(path, active.setup, active.samples)
        except OSError as exc:
            self._error_dialog("Could not export trace", str(exc))
            return
        self._status_bar.showMessage(f"Exported {path}", 5000)

    def _error_dialog(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    # --- worker → ui slots --------------------------------------------------

    def _on_started(self, _setup: Setup) -> None:
        self._status_bar.showMessage("Running sweep…")

    def _on_sample(self, sample: Sample) -> None:
        self._plot.add_sample(sample)

    def _on_completed(self, sample_count: int, aborted: bool) -> None:
        verb = "Aborted" if aborted else "Done"
        self._status_bar.showMessage(f"{verb} ({sample_count} samples)", 5000)
        if sample_count > 0:
            self._export_btn.setEnabled(True)
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
