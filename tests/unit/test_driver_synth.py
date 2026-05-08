"""Tests for the synthetic-data helpers used by ``MockDriver``."""
from __future__ import annotations

import math

import pytest

from paramctl.driver.synth import sweep_points, synth_readings
from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepDirection,
    SweepMeasurement,
    SweepRange,
    SweepScale,
)


def test_linear_sweep_points_count() -> None:
    rng = SweepRange(start=0.0, stop=1.0, points=11)
    pts = sweep_points(rng)
    assert len(pts) == 11
    assert pts[0] == pytest.approx(0.0)
    assert pts[-1] == pytest.approx(1.0)


def test_linear_sweep_points_step_uniform() -> None:
    rng = SweepRange(start=0.0, stop=2.0, points=21)
    pts = sweep_points(rng)
    diffs = [pts[i + 1] - pts[i] for i in range(len(pts) - 1)]
    assert all(d == pytest.approx(0.1) for d in diffs)


def test_log_sweep_points_decade() -> None:
    rng = SweepRange(start=1e-9, stop=1e-3, points=7, scale=SweepScale.LOG10)
    pts = sweep_points(rng)
    assert pts[0] == pytest.approx(1e-9, rel=1e-9)
    assert pts[-1] == pytest.approx(1e-3, rel=1e-9)
    ratios = [pts[i + 1] / pts[i] for i in range(len(pts) - 1)]
    assert all(r == pytest.approx(10.0, rel=1e-6) for r in ratios)


def test_log_sweep_negative_values_preserve_sign() -> None:
    rng = SweepRange(start=-1e-3, stop=-1e-9, points=7, scale=SweepScale.LOG10)
    pts = sweep_points(rng)
    assert all(p < 0 for p in pts)
    assert pts[0] == pytest.approx(-1e-3)


def test_double_direction_doubles_points_minus_apex() -> None:
    rng = SweepRange(start=0.0, stop=1.0, points=11, direction=SweepDirection.DOUBLE)
    pts = sweep_points(rng)
    assert len(pts) == 21  # 11 forward + 10 reverse
    assert pts[0] == pts[-1] == pytest.approx(0.0)
    assert pts[10] == pytest.approx(1.0)
    assert pts[11] == pytest.approx(pts[9])


def _setup_id_vds_at_vgs(
    vgs_value: float = 1.5,
    vds_value: float = 1.0,
    var1_compliance: float | None = 1e-3,
) -> Setup:
    smu1 = ChannelConfig(
        channel_id=ChannelId.SMU1,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.VAR1,
        compliance=var1_compliance,
    )
    smu2 = ChannelConfig(
        channel_id=ChannelId.SMU2,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.CONST,
        source_value=vgs_value,
        compliance=1e-3,
    )
    return Setup(
        channels=[smu1, smu2],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=vds_value, points=11)
        ),
    )


def test_synth_id_increases_with_vds_in_saturation() -> None:
    setup = _setup_id_vds_at_vgs(vgs_value=2.0, vds_value=2.0)
    sweep = setup.measurement
    assert isinstance(sweep, SweepMeasurement)

    samples = [synth_readings(setup, sweep, vds) for vds in [0.0, 0.5, 1.0, 1.5, 2.0]]
    ids = [s[ChannelId.SMU1] for s in samples]

    assert ids[0] < ids[1] < ids[2]
    # Saturation tail: still monotonic because of channel-length modulation.
    assert ids[3] < ids[4]


def test_synth_subthreshold_returns_near_zero() -> None:
    # Vgs below Vth -> drain current is the leakage floor.
    setup = _setup_id_vds_at_vgs(vgs_value=0.3, vds_value=2.0)
    sweep = setup.measurement
    assert isinstance(sweep, SweepMeasurement)

    reading = synth_readings(setup, sweep, 1.0)[ChannelId.SMU1]
    assert abs(reading) < 1e-9


def test_synth_compliance_clamps_current() -> None:
    # Tight compliance forces the model output to clamp.
    setup = _setup_id_vds_at_vgs(vgs_value=3.0, vds_value=2.0, var1_compliance=1e-6)
    sweep = setup.measurement
    assert isinstance(sweep, SweepMeasurement)

    reading = synth_readings(setup, sweep, 1.5, noise_floor=0.0, noise_ratio=0.0)[
        ChannelId.SMU1
    ]
    assert reading == pytest.approx(1e-6, rel=1e-9)


def test_synth_diode_when_no_companion_v_source() -> None:
    # Single SMU sweep — diode model.
    smu1 = ChannelConfig(
        channel_id=ChannelId.SMU1,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.VAR1,
        compliance=1e-3,
    )
    setup = Setup(
        channels=[smu1],
        measurement=SweepMeasurement(
            var1=SweepRange(start=-0.5, stop=0.7, points=13)
        ),
    )
    sweep = setup.measurement
    assert isinstance(sweep, SweepMeasurement)

    rev = synth_readings(setup, sweep, -0.3, noise_floor=0.0, noise_ratio=0.0)[
        ChannelId.SMU1
    ]
    fwd = synth_readings(setup, sweep, 0.6, noise_floor=0.0, noise_ratio=0.0)[
        ChannelId.SMU1
    ]
    # Forward bias produces orders of magnitude more current than reverse.
    assert math.copysign(1, rev) == -1 or rev == pytest.approx(0.0, abs=1e-12)
    assert fwd > 1e-7


def test_synth_omits_disabled_and_passive_channels() -> None:
    smu1 = ChannelConfig(
        channel_id=ChannelId.SMU1,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.VAR1,
        compliance=1e-3,
    )
    smu2 = ChannelConfig(
        channel_id=ChannelId.SMU2,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.CONST,
        source_value=1.0,
        compliance=1e-3,
    )
    smu3 = ChannelConfig(channel_id=ChannelId.SMU3, mode=ChannelMode.DISABLED)
    vmu1 = ChannelConfig(channel_id=ChannelId.VMU1, mode=ChannelMode.COMMON)
    setup = Setup(
        channels=[smu1, smu2, smu3, vmu1],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=1.0, points=5)
        ),
    )
    sweep = setup.measurement
    assert isinstance(sweep, SweepMeasurement)

    readings = synth_readings(setup, sweep, 0.5)
    assert ChannelId.SMU1 in readings
    assert ChannelId.SMU2 in readings
    assert ChannelId.SMU3 not in readings
    assert ChannelId.VMU1 not in readings
