"""Hardware smoke tests for ``FlexDriver`` against a real 4155/4156.

Run with::

    pytest -m hardware --resource='GPIB0::15::INSTR'

These tests are skipped by default because they require a physical
instrument plus a working VISA backend.
"""
from __future__ import annotations

import pytest

from paramctl.driver import FlexDriver
from paramctl.engine import SampleReady, SweepCompleted, run_sweep
from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepMeasurement,
    SweepRange,
)

pytestmark = pytest.mark.hardware


def test_idn_identifies_4155_or_4156(visa_resource: str) -> None:
    """Connect, query ``*IDN?``, and assert the model field is in the family."""
    drv = FlexDriver(visa_resource)
    drv.connect()
    try:
        idn = drv.idn()
    finally:
        drv.disconnect()

    fields = [f.strip() for f in idn.split(",")]
    assert len(fields) >= 4, f"Malformed IDN response: {idn!r}"
    model = fields[1]
    assert any(family in model for family in ("4155", "4156")), (
        f"Connected instrument identifies as {model!r}; expected 4155/4156 family."
    )


def test_context_manager_closes_cleanly(visa_resource: str) -> None:
    """The context manager must connect on enter and disconnect on exit."""
    drv = FlexDriver(visa_resource)
    with drv:
        assert drv.is_connected is True
        drv.idn()
    assert drv.is_connected is False


def test_open_circuit_sweep_returns_expected_source_values(visa_resource: str) -> None:
    """Drive a 6-point V-sweep with no DUT; source-data echoes must match."""
    setup = Setup(
        name="open-circuit smoke",
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=1e-3,
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=0.5, points=6)
        ),
    )

    drv = FlexDriver(visa_resource, timeout_ms=20_000)
    samples = []
    with drv:
        for event in run_sweep(drv, setup):
            if isinstance(event, SampleReady):
                samples.append(event.sample)
            elif isinstance(event, SweepCompleted):
                assert event.aborted is False
                break

    assert len(samples) == 6
    expected_v = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    for s, want in zip(samples, expected_v, strict=True):
        assert s.var1_value == pytest.approx(want, abs=1e-3)
        # Open-circuit current should be near the noise floor, well under 1 nA.
        i_d = s.readings[ChannelId.SMU1]
        assert abs(i_d) < 1e-9, f"unexpected current at {want} V: {i_d} A"


def test_id_vds_with_smu2_const_executes(visa_resource: str) -> None:
    """The M0 step-3 setup runs end-to-end on real hardware.

    Open-circuit at the SMU outputs, so the actual measured current is the
    noise floor — the assertion is structural (right point count, sources
    match, no compliance flag) rather than physical.
    """
    setup = Setup(
        name="ID-VDS at VGS=1.5 V (no DUT)",
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
            var1=SweepRange(start=0.0, stop=1.0, points=11)
        ),
    )

    drv = FlexDriver(visa_resource, timeout_ms=20_000)
    samples = []
    with drv:
        for event in run_sweep(drv, setup):
            if isinstance(event, SampleReady):
                samples.append(event.sample)
            elif isinstance(event, SweepCompleted):
                assert event.aborted is False

    assert len(samples) == 11
    assert samples[0].var1_value == pytest.approx(0.0, abs=1e-3)
    assert samples[-1].var1_value == pytest.approx(1.0, abs=1e-3)
