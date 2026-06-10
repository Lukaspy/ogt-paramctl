"""Runs a :class:`PhotoIvCampaign`: many IV sweeps under varied illumination.

Like :func:`paramctl.engine.runner.run_sweep`, this is a Qt-free generator
that streams events; the ui layer wraps it in a ``QThread`` worker and tests
drive it directly with a ``MockDriver`` + ``MockLightSource``.

Loop, per illumination step:

    apply light state (set wavelength+intensity, or all-off for dark)
    dwell step.settle_s
    run one IV sweep (delegates to run_sweep)        -> StepSample * N
    emit StepCompleted (samples travel with it for the writer)
    dwell campaign.inter_step_delay_s

The light source's lifecycle is owned here (connect at start, all-off +
disconnect in a finally), mirroring the MFIA C-f experiment. The analyzer
driver is owned by the caller and must already be connected -- identical to
``run_sweep``'s contract, so the same connected driver is reused across
every step.

Cancellation: the caller sets the shared ``abort_event`` and (for a blocking
transport read) calls ``driver.abort()``. Settle/delay dwells are sliced so a
Stop is observed within ~1 s, per CLAUDE.md.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator

from ..driver.base import AnalyzerDriver
from ..light.base import LightSource
from ..models.campaign import PhotoIvCampaign
from ..models.illumination import IlluminationStep
from ..models.results import Sample
from .events import (
    CampaignCompleted,
    CampaignEvent,
    CampaignFailed,
    CampaignStarted,
    SampleReady,
    StepCompleted,
    StepSample,
    StepStarted,
    SweepCompleted,
    SweepFailed,
)
from .runner import run_sweep

logger = logging.getLogger(__name__)

Sleeper = Callable[[float, Callable[[], bool]], None]


def run_campaign(
    driver: AnalyzerDriver,
    light: LightSource,
    campaign: PhotoIvCampaign,
    *,
    abort_event: threading.Event | None = None,
    sleeper: Sleeper | None = None,
) -> Iterator[CampaignEvent]:
    """Run a photo-IV campaign and stream its events.

    Args:
        driver: A **connected** analyzer driver (real or mock). Reused across
            every step; the caller owns its connection lifecycle.
        light: The optical source. This function owns its lifecycle: it is
            connected at the start and all-off + disconnected in a finally.
        campaign: The validated campaign specification.
        abort_event: Optional event the caller sets to cancel the run. Settle
            and inter-step delays poll it; the active sweep is cancelled via
            the same event forwarded to :func:`run_sweep`.
        sleeper: Injection point for the settle/delay waits. Defaults to a
            slice-and-poll sleeper; tests pass a no-op to skip real time.

    Yields:
        ``CampaignStarted`` -> per step (``StepStarted`` -> ``StepSample`` * N
        -> ``StepCompleted``) -> terminal ``CampaignCompleted``. A driver
        exception mid-run yields ``CampaignFailed`` and stops the campaign.

    The function never raises out of itself except ``KeyboardInterrupt`` /
    ``SystemExit``; driver failures surface as ``CampaignFailed``.
    """
    abort = abort_event if abort_event is not None else threading.Event()
    sleep = sleeper or _default_sleeper

    steps = campaign.illumination.steps
    yield CampaignStarted(campaign=campaign, total_steps=len(steps))

    steps_completed = 0
    light_connected = False
    try:
        light.connect()
        light_connected = True

        for index, step in enumerate(steps):
            if abort.is_set():
                break

            _apply_illumination(light, step)
            yield StepStarted(step_index=index, step=step)

            sleep(step.settle_s, abort.is_set)
            if abort.is_set():
                break

            # One measurement may be several sweeps run back-to-back (e.g. a
            # dual-polarity 0->+7 V / 0->-7 V pair). No delay between them --
            # they are one logical measurement; delays sit between steps.
            step_aborted = False
            for curve_index, (curve_label, setup) in enumerate(campaign.setups_for_step()):
                if abort.is_set():
                    step_aborted = True
                    break

                samples: list[Sample] = []
                curve_aborted = False
                failed = False
                try:
                    for event in run_sweep(driver, setup, abort_event=abort):
                        if isinstance(event, SampleReady):
                            samples.append(event.sample)
                            yield StepSample(
                                step_index=index,
                                sample=event.sample,
                                curve_index=curve_index,
                                curve_label=curve_label,
                            )
                        elif isinstance(event, SweepCompleted):
                            curve_aborted = event.aborted
                        elif isinstance(event, SweepFailed):
                            failed = True
                            logger.exception(
                                "run_campaign: step %d curve %d sweep failed",
                                index, curve_index, exc_info=event.exception,
                            )
                            yield CampaignFailed(
                                exception=event.exception, step_index=index
                            )
                except (KeyboardInterrupt, SystemExit):
                    raise

                if failed:
                    return

                yield StepCompleted(
                    step_index=index,
                    step=step,
                    samples=samples,
                    aborted=curve_aborted,
                    curve_index=curve_index,
                    curve_label=curve_label,
                )

                if curve_aborted or abort.is_set():
                    step_aborted = True
                    break

            steps_completed += 1
            if step_aborted:
                break

            # Per-step trailing delay overrides the campaign default when set.
            delay = (
                step.post_delay_s
                if step.post_delay_s is not None
                else campaign.inter_step_delay_s
            )
            sleep(delay, abort.is_set)
            if abort.is_set():
                break
    finally:
        try:
            light.all_off()
        except Exception:
            logger.exception("run_campaign: light.all_off() raised during cleanup")
        if light_connected:
            try:
                light.disconnect()
            except Exception:
                logger.exception("run_campaign: light.disconnect() raised during cleanup")

    yield CampaignCompleted(aborted=abort.is_set(), steps_completed=steps_completed)


def _apply_illumination(light: LightSource, step: IlluminationStep) -> None:
    """Put the source into the step's light state."""
    if step.is_dark or step.wavelength_nm is None:
        light.all_off()
        return
    light.set_intensity(step.wavelength_nm, step.intensity_pct)


def _default_sleeper(seconds: float, stopped: Callable[[], bool]) -> None:
    """Sleep ``seconds`` in <=0.25 s slices, returning early if ``stopped()``."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if stopped():
            return
        time.sleep(min(0.25, max(0.0, end - time.monotonic())))


__all__ = ["run_campaign"]
