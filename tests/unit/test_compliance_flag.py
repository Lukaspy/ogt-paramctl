"""End-to-end tests for the compliance-hit flag through the stack.

Mock-side: tight compliance forces synth to clamp -> Sample.compliance_hit=True.
Plot-side: a sample with compliance_hit=True is recorded as such on the
active run's per-channel compliance list.
"""
from __future__ import annotations

import pytest

from paramctl.driver import MockDriver
from paramctl.driver.flex_protocol import parse_field
from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Sample,
    Setup,
    SweepMeasurement,
    SweepRange,
)
from paramctl.ui.widgets import PlotView


def _hit_compliance_setup() -> Setup:
    """Tight 1 nA compliance with a strong gate forces the MOSFET model to clamp."""
    return Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=1e-9,
            ),
            ChannelConfig(
                channel_id=ChannelId.SMU2,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.CONST,
                source_value=3.0,
                compliance=1e-3,
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=2.0, points=11)
        ),
    )


def _no_compliance_setup() -> Setup:
    return Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=1.0,  # 1 A — never hit
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=0.5, points=6)
        ),
    )


def test_mock_marks_clamped_samples_as_compliance_hit() -> None:
    drv = MockDriver()
    drv.connect()
    samples = list(drv.measure(_hit_compliance_setup()))
    drv.disconnect()

    # First few samples (Vds near zero) should not hit compliance, later
    # ones definitely should.
    assert any(s.compliance_hit for s in samples), (
        "tight compliance should have triggered for at least one sample"
    )


def test_mock_does_not_flag_uncomplied_samples() -> None:
    drv = MockDriver()
    drv.connect()
    samples = list(drv.measure(_no_compliance_setup()))
    drv.disconnect()
    assert not any(s.compliance_hit for s in samples)


def test_plot_view_records_per_point_compliance(qtbot) -> None:
    view = PlotView()
    qtbot.addWidget(view)
    view.begin_run(_no_compliance_setup())

    # Synthesise a stream of samples, every other one flagged for compliance.
    for i, vds in enumerate([0.0, 0.1, 0.2, 0.3, 0.4]):
        view.add_sample(
            Sample(
                index=i,
                var1_value=vds,
                readings={ChannelId.SMU1: 1e-6 * (i + 1)},
                compliance_hit=(i % 2 == 1),
            )
        )

    active = view.active_run
    assert active is not None
    flags = active.compliance_by_channel[ChannelId.SMU1]
    assert flags == [False, True, False, True, False]


def test_sample_default_compliance_hit_is_false() -> None:
    s = Sample(index=0, var1_value=0.0, readings={ChannelId.SMU1: 1e-6})
    assert s.compliance_hit is False


def test_sample_round_trips_compliance_hit() -> None:
    s = Sample(
        index=0, var1_value=0.0, readings={ChannelId.SMU1: 1e-6}, compliance_hit=True
    )
    payload = s.model_dump()
    rebuilt = Sample.model_validate(payload)
    assert rebuilt.compliance_hit is True


def test_real_capture_status_008_means_compliance() -> None:
    """The 008 status code on a 4155B field means compliance reached.

    Empirically captured 2026-05-08 by I-sourcing 1 mA into open circuit
    with Vcomp=2 V; status flipped from 000 to 008 the moment the
    instrument railed to the voltage compliance limit.
    """
    pre_compliance = parse_field("000AV-5.328400E-02")
    in_compliance = parse_field("008AV+2.000028E+00")
    assert pre_compliance.compliance_hit is False
    assert in_compliance.compliance_hit is True


def test_real_capture_compliance_value_matches_setting() -> None:
    field = parse_field("008AV+2.000028E+00")
    assert field.value == pytest.approx(2.0, abs=1e-3)
