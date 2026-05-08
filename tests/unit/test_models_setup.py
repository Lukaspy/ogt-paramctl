"""Integration-flavoured tests for the ``Setup`` aggregate model.

These exercise the cross-channel and channel-vs-measurement validation
that lives in ``Setup._validate_setup``.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from paramctl.models import (
    CURRENT_SCHEMA_VERSION,
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelLimits,
    ChannelMode,
    Setup,
    SpotMeasurement,
    SweepMeasurement,
    SweepRange,
    Var1PrimeLink,
)


def _smu1_var1(compliance: float = 1e-3) -> ChannelConfig:
    return ChannelConfig(
        channel_id=ChannelId.SMU1,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.VAR1,
        compliance=compliance,
        label="Drain",
    )


def _smu2_const(value: float = 1.0, compliance: float = 1e-3) -> ChannelConfig:
    return ChannelConfig(
        channel_id=ChannelId.SMU2,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.CONST,
        source_value=value,
        compliance=compliance,
        label="Gate",
    )


def _basic_sweep() -> SweepMeasurement:
    return SweepMeasurement(var1=SweepRange(start=0.0, stop=2.0, points=21))


def test_m0_step3_target_setup() -> None:
    """The exact setup M0 step 3 mandates: SMU1=VAR1 V-sweep, SMU2=CONST V."""
    setup = Setup(
        name="ID-VDS @ fixed VGS",
        channels=[_smu1_var1(), _smu2_const(value=1.0)],
        measurement=_basic_sweep(),
    )
    assert setup.schema_version == CURRENT_SCHEMA_VERSION
    assert len(setup.channels) == 2
    assert isinstance(setup.measurement, SweepMeasurement)


def test_setup_round_trips_through_dump() -> None:
    setup = Setup(
        name="round-trip",
        channels=[_smu1_var1(), _smu2_const()],
        measurement=_basic_sweep(),
    )
    payload = setup.model_dump()
    rebuilt = Setup.model_validate(payload)
    assert rebuilt == setup


def test_setup_requires_at_least_one_channel() -> None:
    with pytest.raises(ValidationError):
        Setup(channels=[], measurement=_basic_sweep())


def test_duplicate_channel_id_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate channel_id"):
        Setup(
            channels=[_smu1_var1(), _smu1_var1()],
            measurement=_basic_sweep(),
        )


def test_sweep_requires_exactly_one_var1() -> None:
    with pytest.raises(ValidationError, match="exactly one VAR1"):
        Setup(channels=[_smu2_const()], measurement=_basic_sweep())


def test_sweep_two_var1_channels_rejected() -> None:
    second_var1 = ChannelConfig(
        channel_id=ChannelId.SMU2,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.VAR1,
        compliance=1e-3,
    )
    with pytest.raises(ValidationError, match="exactly one VAR1"):
        Setup(channels=[_smu1_var1(), second_var1], measurement=_basic_sweep())


def test_var2_channel_without_var2_range_rejected() -> None:
    var2_chan = ChannelConfig(
        channel_id=ChannelId.SMU2,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.VAR2,
        compliance=1e-3,
    )
    with pytest.raises(ValidationError, match="VAR2 but no var2 sweep"):
        Setup(channels=[_smu1_var1(), var2_chan], measurement=_basic_sweep())


def test_var2_range_without_var2_channel_rejected() -> None:
    sweep_with_var2 = SweepMeasurement(
        var1=SweepRange(start=0.0, stop=1.0, points=11),
        var2=SweepRange(start=0.5, stop=1.5, points=3),
    )
    with pytest.raises(ValidationError, match="0 VAR2 channels"):
        Setup(
            channels=[_smu1_var1(), _smu2_const()],
            measurement=sweep_with_var2,
        )


def test_var1_prime_pairing_required() -> None:
    sweep_with_link = SweepMeasurement(
        var1=SweepRange(start=0.0, stop=1.0, points=11),
        var1_prime=Var1PrimeLink(ratio=1.0, offset=0.0),
    )
    with pytest.raises(ValidationError, match="0 VAR1_PRIME channels"):
        Setup(
            channels=[_smu1_var1(), _smu2_const()],
            measurement=sweep_with_link,
        )


def test_spot_measurement_rejects_sweep_function_channels() -> None:
    with pytest.raises(ValidationError, match="cannot have channels tagged VAR1"):
        Setup(
            channels=[_smu1_var1(), _smu2_const()],
            measurement=SpotMeasurement(),
        )


def test_safety_ceiling_rejects_oversize_source() -> None:
    setup_payload = {
        "channels": [_smu1_var1(), _smu2_const(value=25.0)],
        "measurement": _basic_sweep(),
        "safety_ceilings": {
            ChannelId.SMU2.value: ChannelLimits(max_voltage=20.0, max_current=0.1).model_dump(),
        },
    }
    with pytest.raises(ValidationError, match="SMU2 source value 25.0 V exceeds"):
        Setup.model_validate(setup_payload)


def test_safety_ceiling_rejects_oversize_compliance() -> None:
    with pytest.raises(ValidationError, match="exceeds ceiling"):
        Setup(
            channels=[
                _smu1_var1(compliance=2.0),  # 2 A is huge for an SMU
                _smu2_const(value=1.0),
            ],
            measurement=_basic_sweep(),
            safety_ceilings={
                ChannelId.SMU1: ChannelLimits(max_voltage=20.0, max_current=0.1),
            },
        )


def test_safety_ceiling_within_limits_ok() -> None:
    setup = Setup(
        channels=[_smu1_var1(), _smu2_const(value=1.0)],
        measurement=_basic_sweep(),
        safety_ceilings={
            ChannelId.SMU1: ChannelLimits(max_voltage=20.0, max_current=0.1),
            ChannelId.SMU2: ChannelLimits(max_voltage=20.0, max_current=0.1),
        },
    )
    assert ChannelId.SMU1 in setup.safety_ceilings


def test_setup_is_frozen() -> None:
    setup = Setup(
        channels=[_smu1_var1(), _smu2_const()],
        measurement=_basic_sweep(),
    )
    with pytest.raises(ValidationError):
        setup.name = "renamed"  # type: ignore[misc]


def test_setup_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        Setup.model_validate(
            {
                "channels": [_smu1_var1().model_dump(), _smu2_const().model_dump()],
                "measurement": _basic_sweep().model_dump(),
                "unknown_key": True,
            }
        )


def test_resource_string_optional() -> None:
    setup = Setup(
        channels=[_smu1_var1(), _smu2_const()],
        measurement=_basic_sweep(),
        resource_string="GPIB0::17::INSTR",
    )
    assert setup.resource_string == "GPIB0::17::INSTR"


def test_schema_version_pinned() -> None:
    """Loading a payload with the wrong schema_version should fail loudly.

    A future migration path will accept older versions and upgrade them; for
    now the contract is "v1 only", and that contract is the trigger for the
    migration to be written.
    """
    payload = {
        "schema_version": 2,
        "channels": [_smu1_var1().model_dump(), _smu2_const().model_dump()],
        "measurement": _basic_sweep().model_dump(),
    }
    with pytest.raises(ValidationError):
        Setup.model_validate(payload)
