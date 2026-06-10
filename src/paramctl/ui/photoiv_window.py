"""Photo-IV campaign window: stage a light plan, run it, watch the curves.

Layout mirrors the single-sweep ``MainWindow``: controls on the left, the
multi-trace plot on the right, Run / Stop / Clear on the toolbar. The left
panel adds the campaign-specific pieces -- run metadata + output folder, the
inter-measurement delay, an illumination-sequence builder (wavelength x
intensity matrix with dark interleaving), the resulting step queue, and the
base IV-sweep editor that every step re-runs.

The window never touches VISA or the LED source directly: it builds a
``PhotoIvCampaign`` and hands it to a :class:`CampaignWorker` on a QThread.
"""
from __future__ import annotations

import logging
import threading

from pydantic import ValidationError
from PyQt6.QtCore import QThread
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from ..driver.base import AnalyzerDriver
from ..light.base import LightSource
from ..light.mock import DEFAULT_WAVELENGTHS_NM
from ..models.campaign import PhotoIvCampaign
from ..models.illumination import IlluminationSequence
from ..models.measurement import SweepRange
from ..models.results import Sample
from ..models.setup import Setup
from .photoiv_workers import CampaignWorker
from .widgets import PlotView, SetupEditor

logger = logging.getLogger(__name__)

_SPIN_MIN_WIDTH = 110


def _spin(value: float, lo: float, hi: float, step: float, decimals: int = 3) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(decimals)
    s.setSingleStep(step)
    s.setValue(value)
    s.setMinimumWidth(_SPIN_MIN_WIDTH)
    return s


class PhotoIvWindow(QMainWindow):
    """Stage and run a photo-IV campaign against a driver + light source."""

    def __init__(
        self,
        driver: AnalyzerDriver,
        light: LightSource,
        initial_setup: Setup,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._driver = driver
        self._light = light
        self._thread: QThread | None = None
        self._worker: CampaignWorker | None = None
        self._abort_event: threading.Event | None = None
        self._sequence: IlluminationSequence | None = None
        self._campaign: PhotoIvCampaign | None = None
        self._last_curve_key: tuple[int, int] | None = None

        self.setWindowTitle("paramctl — photo-IV campaign")
        self._build_ui()
        self._editor.populate_from(initial_setup)
        self._wire()

    # --- UI assembly --------------------------------------------------------

    def _build_ui(self) -> None:
        self._run_btn = QPushButton("Run campaign")
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._clear_btn = QPushButton("Clear plot")
        self._log_y_check = QCheckBox("Log Y")
        self._idn_label = QLabel(
            f"Analyzer: {type(self._driver).__name__}   "
            f"LED: {type(self._light).__name__}"
        )

        toolbar = QHBoxLayout()
        toolbar.addWidget(self._run_btn)
        toolbar.addWidget(self._stop_btn)
        toolbar.addWidget(self._clear_btn)
        toolbar.addWidget(self._log_y_check)
        toolbar.addStretch()
        toolbar.addWidget(self._idn_label)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)
        controls_layout.addWidget(self._build_metadata_group())
        controls_layout.addWidget(self._build_sequence_group())
        controls_layout.addWidget(self._build_ranges_group())
        controls_layout.addWidget(self._build_queue_group())
        controls_layout.addWidget(
            QLabel("Base IV setup (channels, compliance, integration;\n"
                   "VAR1 range used only when dual-polarity is off):")
        )
        self._editor = SetupEditor()
        controls_layout.addWidget(self._editor)
        controls_layout.addStretch()

        controls_scroll = QScrollArea()
        controls_scroll.setWidget(controls)
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setMinimumWidth(440)

        self._plot = PlotView()

        splitter = QSplitter()
        splitter.addWidget(controls_scroll)
        splitter.addWidget(self._plot)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([480, 720])

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

    def _build_metadata_group(self) -> QGroupBox:
        box = QGroupBox("Run")
        form = QFormLayout(box)
        self._device_edit = QLineEdit()
        self._substrate_edit = QLineEdit()
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setFixedHeight(48)
        self._outdir_edit = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._on_browse_outdir)
        outdir_row = QHBoxLayout()
        outdir_row.addWidget(self._outdir_edit, stretch=1)
        outdir_row.addWidget(browse)
        outdir_widget = QWidget()
        outdir_widget.setLayout(outdir_row)

        self._delay_spin = _spin(0.0, 0.0, 86_400.0, 1.0, decimals=1)
        self._delay_spin.setSuffix(" s")

        form.addRow("Device id", self._device_edit)
        form.addRow("Substrate", self._substrate_edit)
        form.addRow("Notes", self._notes_edit)
        form.addRow("Output folder", outdir_widget)
        form.addRow("Delay between measurements", self._delay_spin)
        return box

    def _build_sequence_group(self) -> QGroupBox:
        box = QGroupBox("Illumination plan")
        outer = QVBoxLayout(box)

        mode_form = QFormLayout()
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Series: dark-pre, all intensities, dark-post (per λ)", "series")
        self._mode_combo.addItem("Matrix: dark between every step", "matrix")
        self._mode_combo.currentIndexChanged.connect(self._update_mode_fields)
        mode_form.addRow("Plan type", self._mode_combo)
        outer.addLayout(mode_form)

        outer.addWidget(QLabel("Wavelengths (nm):"))
        wl_row = QHBoxLayout()
        self._wl_checks: dict[float, QCheckBox] = {}
        for wl in DEFAULT_WAVELENGTHS_NM:
            cb = QCheckBox(f"{int(wl)}")
            self._wl_checks[wl] = cb
            wl_row.addWidget(cb)
        wl_widget = QWidget()
        wl_widget.setLayout(wl_row)
        outer.addWidget(wl_widget)

        form = QFormLayout()
        self._intensity_edit = QLineEdit("1, 3, 10, 30, 100")
        self._intensity_edit.setToolTip("Comma-separated drive percents, e.g. 1, 3, 10, 30, 100")
        self._light_settle = _spin(30.0, 0.0, 36_000.0, 1.0, decimals=1)
        self._light_settle.setSuffix(" s")
        self._dark_settle = _spin(60.0, 0.0, 36_000.0, 1.0, decimals=1)
        self._dark_settle.setSuffix(" s")
        form.addRow("Intensities (%)", self._intensity_edit)
        form.addRow("Lit settle", self._light_settle)
        form.addRow("Dark settle", self._dark_settle)
        outer.addLayout(form)

        # Series-mode timing (the distinct delays the grouped plan needs).
        self._series_box = QGroupBox("Series timing")
        sform = QFormLayout(self._series_box)
        self._inter_light_delay = _spin(0.0, 0.0, 36_000.0, 1.0, decimals=1)
        self._inter_light_delay.setSuffix(" s")
        self._post_series_delay = _spin(0.0, 0.0, 36_000.0, 1.0, decimals=1)
        self._post_series_delay.setSuffix(" s")
        self._inter_wl_delay = _spin(0.0, 0.0, 36_000.0, 1.0, decimals=1)
        self._inter_wl_delay.setSuffix(" s")
        sform.addRow("Delay between light sweeps", self._inter_light_delay)
        sform.addRow("Delay before dark-post", self._post_series_delay)
        sform.addRow("Delay between wavelengths", self._inter_wl_delay)
        outer.addWidget(self._series_box)

        # Matrix-mode option.
        self._interleave_check = QCheckBox("Interleave dark (pre / post each step)")
        self._interleave_check.setChecked(True)
        outer.addWidget(self._interleave_check)

        self._generate_btn = QPushButton("Generate sequence")
        self._generate_btn.clicked.connect(self._on_generate_sequence)
        outer.addWidget(self._generate_btn)

        self._update_mode_fields()
        return box

    def _build_ranges_group(self) -> QGroupBox:
        box = QGroupBox("Sweep ranges (each measurement)")
        form = QFormLayout(box)
        self._dual_check = QCheckBox("Dual polarity: 0 to +V and 0 to -V (2 curves each)")
        self._dual_check.setChecked(True)
        self._dual_v = _spin(7.0, 0.1, 200.0, 1.0, decimals=2)
        self._dual_v.setSuffix(" V")
        self._dual_points = QSpinBox()
        self._dual_points.setRange(2, 100_001)
        self._dual_points.setValue(71)
        self._dual_points.setMinimumWidth(_SPIN_MIN_WIDTH)
        self._dual_check.toggled.connect(self._dual_v.setEnabled)
        self._dual_check.toggled.connect(self._dual_points.setEnabled)
        form.addRow("", self._dual_check)
        form.addRow("Magnitude |V|", self._dual_v)
        form.addRow("Points per sweep", self._dual_points)
        return box

    def _update_mode_fields(self) -> None:
        is_series = self._mode_combo.currentData() == "series"
        self._series_box.setEnabled(is_series)
        self._interleave_check.setEnabled(not is_series)

    def _build_queue_group(self) -> QGroupBox:
        box = QGroupBox("Staged measurements (one IV per row)")
        layout = QVBoxLayout(box)
        self._queue = QListWidget()
        self._queue.setMinimumHeight(140)
        layout.addWidget(self._queue)
        return box

    def _wire(self) -> None:
        self._run_btn.clicked.connect(self._on_run)
        self._stop_btn.clicked.connect(self._on_stop)
        self._clear_btn.clicked.connect(self._on_clear)
        self._log_y_check.toggled.connect(self._plot.set_log_y)
        self._plot.cursor_changed.connect(self._cursor_label.setText)

    # --- sequence building --------------------------------------------------

    def _on_browse_outdir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose output folder")
        if path:
            self._outdir_edit.setText(path)

    @staticmethod
    def _parse_float_list(raw: str) -> list[float]:
        out: list[float] = []
        for token in raw.replace(";", ",").split(","):
            token = token.strip()
            if token:
                out.append(float(token))
        return out

    def _on_generate_sequence(self) -> None:
        wavelengths = [wl for wl, cb in self._wl_checks.items() if cb.isChecked()]
        if not wavelengths:
            self._status_bar.showMessage("Select at least one wavelength.", 6000)
            return
        try:
            intensities = self._parse_float_list(self._intensity_edit.text())
        except ValueError:
            self._status_bar.showMessage(
                "Intensities must be comma-separated numbers, e.g. 25, 50, 100", 8000
            )
            return
        if not intensities:
            self._status_bar.showMessage("Enter at least one intensity percent.", 6000)
            return

        try:
            if self._mode_combo.currentData() == "series":
                sequence = IlluminationSequence.intensity_series_per_wavelength(
                    sorted(wavelengths),
                    intensities,
                    dark_settle_s=self._dark_settle.value(),
                    light_settle_s=self._light_settle.value(),
                    inter_light_delay_s=self._inter_light_delay.value(),
                    post_series_delay_s=self._post_series_delay.value(),
                    inter_wavelength_delay_s=self._inter_wl_delay.value(),
                )
            else:
                sequence = IlluminationSequence.wavelength_intensity_matrix(
                    sorted(wavelengths),
                    intensities,
                    interleave_dark=self._interleave_check.isChecked(),
                    light_settle_s=self._light_settle.value(),
                    dark_settle_s=self._dark_settle.value(),
                )
        except (ValidationError, ValueError) as exc:
            self._status_bar.showMessage(f"Could not build sequence: {exc}", 8000)
            return

        self._sequence = sequence
        self._populate_queue(sequence)
        curves = 2 if self._dual_check.isChecked() else 1
        self._status_bar.showMessage(
            f"Staged {len(sequence)} measurements x {curves} curve(s) "
            f"= {len(sequence) * curves} sweeps "
            f"({len(wavelengths)} wavelengths, {len(intensities)} intensities).",
            8000,
        )

    def _populate_queue(self, sequence: IlluminationSequence) -> None:
        self._queue.clear()
        for step in sequence.steps:
            self._queue.addItem(QListWidgetItem(f"○ {step.label}"))

    def _set_queue_status(self, index: int, marker: str, suffix: str = "") -> None:
        item = self._queue.item(index)
        if item is None:
            return
        label = item.text().split(" ", 1)[-1].split("   ")[0]
        text = f"{marker} {label}"
        if suffix:
            text += f"   {suffix}"
        item.setText(text)

    # --- run / stop / clear -------------------------------------------------

    def _build_campaign(self) -> PhotoIvCampaign | None:
        if self._sequence is None:
            self._status_bar.showMessage(
                "Generate an illumination sequence before running.", 8000
            )
            return None
        try:
            base = self._editor.current_setup()
        except ValidationError as exc:
            first = exc.errors()[0]
            loc = ".".join(str(p) for p in first.get("loc", ()))
            self._status_bar.showMessage(
                f"Base setup invalid: {loc}: {first.get('msg', exc)}", 10000
            )
            return None
        sweep_ranges: list[SweepRange] | None = None
        if self._dual_check.isChecked():
            v = self._dual_v.value()
            n = self._dual_points.value()
            sweep_ranges = [
                SweepRange(start=0.0, stop=v, points=n),
                SweepRange(start=0.0, stop=-v, points=n),
            ]
        try:
            return PhotoIvCampaign(
                base_setup=base,
                illumination=self._sequence,
                sweep_ranges=sweep_ranges,
                inter_step_delay_s=self._delay_spin.value(),
                device_id=self._device_edit.text().strip(),
                substrate_type=self._substrate_edit.text().strip(),
                notes=self._notes_edit.toPlainText().strip(),
                output_dir=self._outdir_edit.text().strip(),
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            self._status_bar.showMessage(f"Campaign invalid: {first.get('msg', exc)}", 10000)
            return None

    def _on_run(self) -> None:
        if self._thread is not None:
            return
        campaign = self._build_campaign()
        if campaign is None:
            return

        self._campaign = campaign
        self._plot.clear_history()
        self._last_curve_key = None
        self._abort_event = threading.Event()
        worker = CampaignWorker(self._driver, self._light, campaign, self._abort_event)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.started.connect(self._on_started)
        worker.step_started.connect(self._on_step_started)
        worker.step_sample.connect(self._on_step_sample)
        worker.step_done.connect(self._on_step_done)
        worker.failed.connect(self._on_failed)
        worker.completed.connect(self._on_completed)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._cleanup_thread)

        self._worker = worker
        self._thread = thread
        self._run_btn.setEnabled(False)
        self._generate_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        if not campaign.output_dir:
            self._status_bar.showMessage(
                "No output folder set — curves will plot but not be saved.", 8000
            )
        thread.start()

    def _on_stop(self) -> None:
        if self._abort_event is None:
            return
        self._status_bar.showMessage("Aborting…")
        self._abort_event.set()
        try:
            self._driver.abort()
        except Exception:
            logger.exception("PhotoIvWindow: driver.abort() raised")

    def _on_clear(self) -> None:
        if self._thread is not None:
            self._status_bar.showMessage("Cannot clear while a campaign is running.", 5000)
            return
        self._plot.clear_history()
        self._status_bar.showMessage("Plot cleared.", 3000)

    # --- worker → ui slots --------------------------------------------------

    def _on_started(self, total_steps: int) -> None:
        self._status_bar.showMessage(f"Running campaign — {total_steps} measurements…")

    def _on_step_started(self, index: int, _label: str) -> None:
        self._set_queue_status(index, "▶")
        self._queue.setCurrentRow(index)

    def _on_step_sample(self, step_index: int, curve_index: int, sample: Sample) -> None:
        # A new (step, curve) means a new sweep — start a fresh plot trace so
        # each polarity/level is its own curve, with prior ones kept as history.
        key = (step_index, curve_index)
        if key != self._last_curve_key:
            if self._campaign is not None:
                self._plot.begin_run(self._campaign.base_setup)
            self._last_curve_key = key
        self._plot.add_sample(sample)

    def _on_step_done(self, index: int, _curve_index: int, _label: str, path: str) -> None:
        suffix = path.rsplit("/", 1)[-1] if path else "(not saved)"
        self._set_queue_status(index, "✓", suffix)

    def _on_failed(self, exc: BaseException, index: int) -> None:
        where = f"step {index}" if index >= 0 else "campaign"
        self._status_bar.showMessage(f"Failed at {where}: {exc}", 12000)

    def _on_completed(self, aborted: bool, steps_completed: int) -> None:
        verb = "Aborted" if aborted else "Done"
        self._status_bar.showMessage(
            f"{verb} — {steps_completed} measurement(s) completed.", 8000
        )

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
        self._generate_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)

    def closeEvent(self, a0: QCloseEvent | None) -> None:
        if self._abort_event is not None:
            self._abort_event.set()
        if self._thread is not None:
            try:
                self._driver.abort()
            except Exception:
                logger.exception("PhotoIvWindow: driver.abort() during close raised")
            self._thread.quit()
            self._thread.wait(2000)
        super().closeEvent(a0)


__all__ = ["PhotoIvWindow"]
