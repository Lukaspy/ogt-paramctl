"""End-to-end sweep against ``MockDriver``: the M0 step-3+4 vertical slice.

Drives the engine with the exact setup mandated by CLAUDE.md M0 step 3
(SMU1 = VAR1 V-sweep, SMU2 = CONST V) and checks that the resulting sample
stream is well-formed enough to plot.
"""
from __future__ import annotations

from itertools import pairwise

from paramctl.driver import MockDriver
from paramctl.engine import (
    SampleReady,
    SweepCompleted,
    SweepStarted,
    run_sweep,
)
from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepMeasurement,
    SweepRange,
)


def test_id_vds_sweep_against_mock_produces_plottable_curve() -> None:
    setup = Setup(
        name="ID-VDS at VGS=1.5 V",
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10e-3,
                label="Drain",
            ),
            ChannelConfig(
                channel_id=ChannelId.SMU2,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.CONST,
                source_value=1.5,
                compliance=1e-3,
                label="Gate",
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=2.0, points=21)
        ),
    )

    drv = MockDriver()
    drv.connect()
    try:
        events = list(run_sweep(drv, setup))
    finally:
        drv.disconnect()

    assert isinstance(events[0], SweepStarted)
    samples = [e.sample for e in events if isinstance(e, SampleReady)]
    assert len(samples) == 21

    terminal = events[-1]
    assert isinstance(terminal, SweepCompleted)
    assert terminal.aborted is False
    assert terminal.sample_count == 21

    # Plottability: var1 monotonic, drain current monotonic-ish across the
    # sweep, gate current near zero. We check shape, not exact values, since
    # the synth adds a small random noise term.
    var1_values = [s.var1_value for s in samples]
    assert var1_values is not None
    assert all(a is not None and b is not None and a <= b
               for a, b in pairwise(var1_values))

    drain_currents = [s.readings[ChannelId.SMU1] for s in samples]
    gate_currents = [s.readings[ChannelId.SMU2] for s in samples]

    assert drain_currents[0] < drain_currents[-1]
    assert all(abs(g) < 1e-9 for g in gate_currents)


def test_double_direction_sweep_returns_to_start() -> None:
    from paramctl.models import SweepDirection

    setup = Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=1e-3,
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(
                start=0.0,
                stop=1.0,
                points=11,
                direction=SweepDirection.DOUBLE,
            )
        ),
    )
    drv = MockDriver()
    drv.connect()
    try:
        events = list(run_sweep(drv, setup))
    finally:
        drv.disconnect()

    samples = [e.sample for e in events if isinstance(e, SampleReady)]
    assert len(samples) == 21  # 11 forward + 10 reverse
    assert samples[0].var1_value == samples[-1].var1_value
