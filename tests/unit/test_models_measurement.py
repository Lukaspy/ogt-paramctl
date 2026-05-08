"""Unit tests for sweep / sampling / spot measurement models."""
from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from paramctl.models import (
    IntegrationTime,
    MeasurementMode,
    SamplingMeasurement,
    SpotMeasurement,
    SweepDirection,
    SweepMeasurement,
    SweepRange,
    SweepScale,
    Var1PrimeLink,
)


def test_sweep_range_minimal() -> None:
    rng = SweepRange(start=0.0, stop=1.0, points=11)
    assert rng.points == 11
    assert rng.scale is SweepScale.LINEAR
    assert rng.direction is SweepDirection.SINGLE


def test_sweep_range_negative_linear_ok() -> None:
    rng = SweepRange(start=-2.0, stop=-1.0, points=5)
    assert rng.start < rng.stop


def test_sweep_range_zero_span_rejected() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        SweepRange(start=1.0, stop=1.0, points=10)


def test_sweep_range_log_cannot_cross_zero() -> None:
    with pytest.raises(ValidationError, match="log sweep cannot cross"):
        SweepRange(start=-1.0, stop=1.0, points=10, scale=SweepScale.LOG10)


def test_sweep_range_log_negative_decade_ok() -> None:
    rng = SweepRange(start=-1e-9, stop=-1e-3, points=20, scale=SweepScale.LOG10)
    assert rng.scale is SweepScale.LOG10


def test_sweep_range_minimum_two_points() -> None:
    with pytest.raises(ValidationError):
        SweepRange(start=0.0, stop=1.0, points=1)


def test_sweep_measurement_minimal() -> None:
    meas = SweepMeasurement(
        var1=SweepRange(start=0.0, stop=2.0, points=21),
    )
    assert meas.kind == "sweep"
    assert meas.integration is IntegrationTime.MEDIUM
    assert meas.var2 is None
    assert meas.var1_prime is None


def test_sweep_measurement_with_var2_and_var1_prime() -> None:
    meas = SweepMeasurement(
        var1=SweepRange(start=0.0, stop=2.0, points=21),
        var2=SweepRange(start=0.5, stop=1.5, points=3),
        var1_prime=Var1PrimeLink(ratio=2.0, offset=0.1),
        hold_time=0.05,
        delay_time=0.01,
        integration=IntegrationTime.LONG,
    )
    assert meas.var2 is not None
    assert meas.var1_prime is not None
    assert meas.var1_prime.ratio == 2.0
    assert meas.integration is IntegrationTime.LONG


def test_sweep_hold_and_delay_must_be_nonneg() -> None:
    with pytest.raises(ValidationError):
        SweepMeasurement(
            var1=SweepRange(start=0.0, stop=1.0, points=11), hold_time=-0.01
        )


def test_spot_measurement_default() -> None:
    spot = SpotMeasurement()
    assert spot.kind == "spot"
    assert spot.integration is IntegrationTime.MEDIUM


def test_sampling_minimum_constraints() -> None:
    samp = SamplingMeasurement(interval=0.01, points=100)
    assert samp.kind == "sampling"
    with pytest.raises(ValidationError):
        SamplingMeasurement(interval=0.0, points=100)
    with pytest.raises(ValidationError):
        SamplingMeasurement(interval=0.01, points=1)


def test_measurement_mode_discriminator_dispatches_on_kind() -> None:
    adapter: TypeAdapter[MeasurementMode] = TypeAdapter(MeasurementMode)

    sweep = adapter.validate_python(
        {"kind": "sweep", "var1": {"start": 0.0, "stop": 1.0, "points": 11}}
    )
    assert isinstance(sweep, SweepMeasurement)

    spot = adapter.validate_python({"kind": "spot"})
    assert isinstance(spot, SpotMeasurement)

    sampling = adapter.validate_python(
        {"kind": "sampling", "interval": 0.01, "points": 100}
    )
    assert isinstance(sampling, SamplingMeasurement)


def test_measurement_mode_unknown_kind_rejected() -> None:
    adapter: TypeAdapter[MeasurementMode] = TypeAdapter(MeasurementMode)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "transient", "foo": "bar"})


def test_sweep_round_trips_through_dump() -> None:
    meas = SweepMeasurement(
        var1=SweepRange(start=-1.0, stop=2.0, points=31, scale=SweepScale.LINEAR),
    )
    payload = meas.model_dump()
    assert payload["kind"] == "sweep"
    rebuilt = SweepMeasurement.model_validate(payload)
    assert rebuilt == meas
