"""Qt worker that runs a photo-IV campaign on a background thread.

Mirrors :class:`SweepWorker`: the engine layer (``run_campaign``) is Qt-free,
and this object -- moved onto a ``QThread`` -- forwards each campaign event as
a Qt signal. It also owns the per-curve CSV write (disk I/O off the GUI
thread, never in the engine), emitting the written path back to the window.

Threading rules (CLAUDE.md): the driver and light I/O live on this worker;
VISA never runs on the Qt main thread; cancellation is a shared
``threading.Event`` plus a direct ``driver.abort()`` from the caller.
"""
from __future__ import annotations

import logging
import threading

from PyQt6.QtCore import QObject, pyqtSignal

from ..driver import list_resources
from ..driver.base import AnalyzerDriver
from ..engine import (
    CampaignCompleted,
    CampaignFailed,
    CampaignStarted,
    StepCompleted,
    StepSample,
    StepStarted,
    run_campaign,
)
from ..light.base import LightSource
from ..models.campaign import PhotoIvCampaign
from ..persistence import write_campaign_curve

logger = logging.getLogger(__name__)


class CampaignWorker(QObject):
    """Runs ``run_campaign`` on its thread and re-emits as Qt signals.

    Signals:
        started(int): total step count, once at the start.
        step_started(int, str): step index, label -- light state applied.
        step_sample(int, int, object): step index, curve index, ``Sample``.
        step_done(int, int, str, str): step index, curve index, step label,
            saved CSV path (``""`` if no output dir was set or write failed).
        failed(object, int): exception, step index, on a mid-run driver error.
        completed(bool, int): aborted, steps_completed, at the end.
        finished(): emitted unconditionally last, so the caller can quit the
            thread off a single terminal signal.
    """

    started = pyqtSignal(int)
    step_started = pyqtSignal(int, str)
    step_sample = pyqtSignal(int, int, object)
    step_done = pyqtSignal(int, int, str, str)
    failed = pyqtSignal(object, int)
    completed = pyqtSignal(bool, int)
    finished = pyqtSignal()

    def __init__(
        self,
        driver: AnalyzerDriver,
        light: LightSource,
        campaign: PhotoIvCampaign,
        abort_event: threading.Event,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._driver = driver
        self._light = light
        self._campaign = campaign
        self._abort_event = abort_event

    def run(self) -> None:
        """Entry point. Connect a ``QThread.started`` signal to this slot."""
        campaign = self._campaign
        try:
            for event in run_campaign(
                self._driver, self._light, campaign, abort_event=self._abort_event
            ):
                if isinstance(event, CampaignStarted):
                    self.started.emit(event.total_steps)
                elif isinstance(event, StepStarted):
                    self.step_started.emit(event.step_index, event.step.label)
                elif isinstance(event, StepSample):
                    self.step_sample.emit(
                        event.step_index, event.curve_index, event.sample
                    )
                elif isinstance(event, StepCompleted):
                    path = self._write_curve(event)
                    self.step_done.emit(
                        event.step_index, event.curve_index, event.step.label, path
                    )
                elif isinstance(event, CampaignFailed):
                    self.failed.emit(event.exception, event.step_index)
                elif isinstance(event, CampaignCompleted):
                    self.completed.emit(event.aborted, event.steps_completed)
        except BaseException as exc:  # surface anything as failed
            logger.exception("CampaignWorker: unexpected exception")
            self.failed.emit(exc, -1)
        finally:
            self.finished.emit()

    def _write_curve(self, event: StepCompleted) -> str:
        """Write one step's curve to the campaign output dir; return its path.

        Returns ``""`` when no output directory is configured or the write
        fails (the failure is logged and surfaced via the status bar by the
        window when it sees an empty path).
        """
        campaign = self._campaign
        if not campaign.output_dir or not event.samples:
            return ""
        step = event.step
        led_current_ma: float | None = None
        optical_power_mw: float | None = None
        if not step.is_dark and step.wavelength_nm is not None:
            led_current_ma = self._light.current_ma_for(
                step.wavelength_nm, step.intensity_pct
            )
            optical_power_mw = self._light.predicted_power_mw(
                step.wavelength_nm, step.intensity_pct
            )
        try:
            path = write_campaign_curve(
                campaign.output_dir,
                campaign,
                step,
                event.samples,
                curve_label=event.curve_label,
                led_current_ma=led_current_ma,
                optical_power_mw=optical_power_mw,
            )
        except OSError:
            logger.exception(
                "CampaignWorker: failed to write curve for step %d curve %d",
                event.step_index, event.curve_index,
            )
            return ""
        return str(path)


class ConnectWorker(QObject):
    """Connects an analyzer driver off the GUI thread and reports its IDN.

    The driver is constructed on the main thread (construction opens no
    transport); only ``connect()`` + ``idn()`` — the actual VISA calls — run
    here, keeping the "no VISA on the Qt main thread" rule intact for the
    in-GUI Connect button.

    Signals:
        done(str): the instrument's IDN string after a successful connect.
        failed(object): the exception, if connect/idn raised.
        finished(): emitted unconditionally last.
    """

    done = pyqtSignal(str)
    failed = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, driver: AnalyzerDriver, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._driver = driver

    def run(self) -> None:
        try:
            self._driver.connect()
            idn = self._driver.idn()
        except Exception as exc:
            logger.exception("ConnectWorker: connect failed")
            self.failed.emit(exc)
        else:
            self.done.emit(idn)
        finally:
            self.finished.emit()


class DiscoveryWorker(QObject):
    """Enumerates VISA resources off the GUI thread.

    ``pyvisa-py`` discovery probes every GPIB minor device and scans TCPIP
    interfaces, which can block for many seconds — far too long for the Qt
    main thread, and a VISA operation besides (CLAUDE.md threading rules).

    Signals:
        done(list): discovered resource strings (may be empty).
        failed(object): the exception, if discovery raised.
        finished(): emitted unconditionally last.
    """

    done = pyqtSignal(list)
    failed = pyqtSignal(object)
    finished = pyqtSignal()

    def run(self) -> None:
        try:
            resources = list_resources()
        except Exception as exc:
            logger.exception("DiscoveryWorker: discovery failed")
            self.failed.emit(exc)
        else:
            self.done.emit(resources)
        finally:
            self.finished.emit()


__all__ = ["CampaignWorker", "ConnectWorker", "DiscoveryWorker"]
