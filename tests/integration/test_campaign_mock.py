"""End-to-end photo-IV campaign against MockDriver + MockLightSource.

No real instrument, no real LED source, no real time (a no-op sleeper skips
the settle/delay dwells). Verifies the event stream, the dark/lit ordering,
per-step sample tagging, light-source lifecycle, and abort behaviour.
"""
from __future__ import annotations

import threading

from paramctl.driver import MockDriver
from paramctl.engine import (
    CampaignCompleted,
    CampaignStarted,
    StepCompleted,
    StepSample,
    StepStarted,
    run_campaign,
)
from paramctl.light import MockLightSource
from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    IlluminationSequence,
    PhotoIvCampaign,
    Setup,
    SweepMeasurement,
    SweepRange,
)

POINTS = 3


def _campaign(delay: float = 0.0) -> PhotoIvCampaign:
    setup = Setup(
        name="diode IV",
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10e-3,
            ),
        ],
        measurement=SweepMeasurement(var1=SweepRange(start=-1.0, stop=1.0, points=POINTS)),
    )
    return PhotoIvCampaign(
        base_setup=setup,
        illumination=IlluminationSequence.intensity_series(385.0, [50.0, 100.0]),
        inter_step_delay_s=delay,
        device_id="dev42",
    )


def _noop_sleeper(_seconds: float, _stopped: object) -> None:
    return None


def _run(campaign: PhotoIvCampaign, led: MockLightSource, abort=None) -> list[object]:
    drv = MockDriver()
    drv.connect()
    try:
        return list(
            run_campaign(drv, led, campaign, abort_event=abort, sleeper=_noop_sleeper)
        )
    finally:
        drv.disconnect()


def test_campaign_event_stream_and_step_count() -> None:
    campaign = _campaign()
    led = MockLightSource()
    events = _run(campaign, led)

    assert isinstance(events[0], CampaignStarted)
    assert events[0].total_steps == len(campaign.illumination)
    assert isinstance(events[-1], CampaignCompleted)
    assert events[-1].aborted is False

    completed = [e for e in events if isinstance(e, StepCompleted)]
    assert len(completed) == len(campaign.illumination)
    assert all(len(e.samples) == POINTS for e in completed)
    # Each step's samples were also streamed live, tagged with the step index.
    for sc in completed:
        live = [
            e for e in events
            if isinstance(e, StepSample) and e.step_index == sc.step_index
        ]
        assert len(live) == POINTS


def test_dark_pre_lights_off_before_first_illuminated_step() -> None:
    campaign = _campaign()
    led = MockLightSource()
    _run(campaign, led)

    names = [c.name for c in led.calls]
    # connect first, all_off (dark_pre) before the first set_intensity, and
    # the source is left off + disconnected at the end.
    assert names[0] == "connect"
    first_set = names.index("set_intensity")
    assert "all_off" in names[:first_set]
    assert names[-1] == "disconnect"
    assert names[-2] == "all_off"


def test_step_started_emitted_for_every_step_in_order() -> None:
    campaign = _campaign()
    led = MockLightSource()
    events = _run(campaign, led)
    started = [e.step_index for e in events if isinstance(e, StepStarted)]
    assert started == list(range(len(campaign.illumination)))


def test_preset_abort_runs_no_steps() -> None:
    campaign = _campaign()
    led = MockLightSource()
    abort = threading.Event()
    abort.set()
    events = _run(campaign, led, abort=abort)

    assert isinstance(events[0], CampaignStarted)
    assert not any(isinstance(e, StepCompleted) for e in events)
    terminal = events[-1]
    assert isinstance(terminal, CampaignCompleted)
    assert terminal.aborted is True
    assert terminal.steps_completed == 0
    # Even an aborted-before-start run leaves the source off + disconnected.
    assert led.is_connected is False


def test_abort_during_settle_stops_after_current_step_start() -> None:
    campaign = _campaign()
    led = MockLightSource()
    abort = threading.Event()

    def _abort_on_first_settle(_seconds: float, _stopped: object) -> None:
        abort.set()  # fire as soon as the first settle dwell is reached

    drv = MockDriver()
    drv.connect()
    try:
        events = list(
            run_campaign(
                drv, led, campaign, abort_event=abort, sleeper=_abort_on_first_settle
            )
        )
    finally:
        drv.disconnect()

    assert any(isinstance(e, StepStarted) for e in events)
    assert not any(isinstance(e, StepCompleted) for e in events)
    terminal = events[-1]
    assert isinstance(terminal, CampaignCompleted)
    assert terminal.aborted is True
    assert terminal.steps_completed == 0


def _dual_campaign() -> PhotoIvCampaign:
    setup = Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10e-3,
            ),
        ],
        measurement=SweepMeasurement(var1=SweepRange(start=-1.0, stop=1.0, points=POINTS)),
    )
    return PhotoIvCampaign(
        base_setup=setup,
        illumination=IlluminationSequence.intensity_series(385.0, [50.0, 100.0]),
        sweep_ranges=[
            SweepRange(start=0.0, stop=7.0, points=POINTS),
            SweepRange(start=0.0, stop=-7.0, points=POINTS),
        ],
        device_id="dev42",
    )


def test_dual_polarity_yields_two_labelled_curves_per_step() -> None:
    campaign = _dual_campaign()
    led = MockLightSource()
    events = _run(campaign, led)

    completed = [e for e in events if isinstance(e, StepCompleted)]
    n_steps = len(campaign.illumination)
    # Two curves per step.
    assert len(completed) == 2 * n_steps
    for step_index in range(n_steps):
        for_step = [e for e in completed if e.step_index == step_index]
        assert [e.curve_index for e in for_step] == [0, 1]
        assert [e.curve_label for e in for_step] == ["0to+7V", "0to-7V"]
        assert all(len(e.samples) == POINTS for e in for_step)

    terminal = events[-1]
    assert isinstance(terminal, CampaignCompleted)
    assert terminal.aborted is False


def test_per_step_post_delay_overrides_campaign_default() -> None:
    # A grouped series with distinct delays: dark_pre(0), 1pct(5), 100pct(9), dark_post(0).
    sequence = IlluminationSequence.intensity_series_per_wavelength(
        [385.0],
        [1.0, 100.0],
        dark_settle_s=2.0,
        light_settle_s=1.0,
        inter_light_delay_s=5.0,
        post_series_delay_s=9.0,
    )
    setup = Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10e-3,
            ),
        ],
        measurement=SweepMeasurement(var1=SweepRange(start=-1.0, stop=1.0, points=POINTS)),
    )
    campaign = PhotoIvCampaign(
        base_setup=setup, illumination=sequence, inter_step_delay_s=99.0
    )

    waits: list[float] = []

    def recording_sleeper(seconds: float, _stopped: object) -> None:
        waits.append(seconds)

    drv = MockDriver()
    drv.connect()
    try:
        list(
            run_campaign(
                drv, MockLightSource(), campaign, sleeper=recording_sleeper
            )
        )
    finally:
        drv.disconnect()

    # Per step the runner sleeps (settle, then trailing delay). The trailing
    # delay comes from each step's post_delay_s, NOT the campaign default (99).
    assert waits == [2.0, 0.0, 1.0, 5.0, 1.0, 9.0, 2.0, 0.0]
