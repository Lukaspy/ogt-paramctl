"""Unit tests for ``ChannelConfig`` and the channel-identity helpers."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelLimits,
    ChannelMode,
    is_smu,
    is_vmu,
    is_vsu,
)


@pytest.mark.parametrize(
    "channel,smu,vsu,vmu",
    [
        (ChannelId.SMU1, True, False, False),
        (ChannelId.SMU4, True, False, False),
        (ChannelId.VSU1, False, True, False),
        (ChannelId.VMU2, False, False, True),
        (ChannelId.GNDU, False, False, False),
    ],
)
def test_channel_classification_helpers(
    channel: ChannelId, smu: bool, vsu: bool, vmu: bool
) -> None:
    assert is_smu(channel) is smu
    assert is_vsu(channel) is vsu
    assert is_vmu(channel) is vmu


def test_smu_v_source_const_minimal() -> None:
    cfg = ChannelConfig(
        channel_id=ChannelId.SMU2,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.CONST,
        source_value=1.5,
        compliance=1e-3,
    )
    assert cfg.channel_id is ChannelId.SMU2
    assert cfg.mode is ChannelMode.V_SOURCE
    assert cfg.compliance == 1e-3


def test_smu_var1_voltage_sweep() -> None:
    cfg = ChannelConfig(
        channel_id=ChannelId.SMU1,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.VAR1,
        compliance=10e-3,
        label="Drain",
    )
    assert cfg.function is ChannelFunction.VAR1
    assert cfg.label == "Drain"


def test_smu_disabled_is_const() -> None:
    cfg = ChannelConfig(
        channel_id=ChannelId.SMU3,
        mode=ChannelMode.DISABLED,
    )
    assert cfg.function is ChannelFunction.CONST


def test_smu_source_requires_compliance() -> None:
    with pytest.raises(ValidationError, match="requires a compliance"):
        ChannelConfig(
            channel_id=ChannelId.SMU1,
            mode=ChannelMode.V_SOURCE,
        )


def test_compliance_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="positive"):
        ChannelConfig(
            channel_id=ChannelId.SMU1,
            mode=ChannelMode.V_SOURCE,
            compliance=0.0,
        )


def test_vmu_cannot_source() -> None:
    with pytest.raises(ValidationError, match="cannot source"):
        ChannelConfig(
            channel_id=ChannelId.VMU1,
            mode=ChannelMode.V_SOURCE,
            compliance=1e-3,
        )


def test_vsu_cannot_i_source() -> None:
    with pytest.raises(ValidationError, match="I_SOURCE not supported"):
        ChannelConfig(
            channel_id=ChannelId.VSU1,
            mode=ChannelMode.I_SOURCE,
            compliance=10.0,
        )


def test_vsu_v_source_does_not_need_compliance() -> None:
    cfg = ChannelConfig(
        channel_id=ChannelId.VSU1,
        mode=ChannelMode.V_SOURCE,
        source_value=2.5,
    )
    assert cfg.compliance is None


def test_gndu_must_be_common() -> None:
    with pytest.raises(ValidationError, match="GNDU is always COMMON"):
        ChannelConfig(channel_id=ChannelId.GNDU, mode=ChannelMode.V_SOURCE)


def test_gndu_common_ok() -> None:
    cfg = ChannelConfig(channel_id=ChannelId.GNDU, mode=ChannelMode.COMMON)
    assert cfg.mode is ChannelMode.COMMON


def test_disabled_cannot_have_sweep_function() -> None:
    with pytest.raises(ValidationError, match="DISABLED channels"):
        ChannelConfig(
            channel_id=ChannelId.SMU2,
            mode=ChannelMode.DISABLED,
            function=ChannelFunction.VAR1,
        )


def test_sweep_function_requires_source_mode() -> None:
    with pytest.raises(ValidationError, match="not a source"):
        ChannelConfig(
            channel_id=ChannelId.SMU2,
            mode=ChannelMode.COMMON,
            function=ChannelFunction.VAR1,
        )


def test_channel_config_is_frozen() -> None:
    cfg = ChannelConfig(
        channel_id=ChannelId.SMU1,
        mode=ChannelMode.V_SOURCE,
        compliance=1e-3,
    )
    with pytest.raises(ValidationError):
        cfg.compliance = 2e-3  # type: ignore[misc]


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        ChannelConfig.model_validate(
            {
                "channel_id": "SMU1",
                "mode": "V_SOURCE",
                "compliance": 1e-3,
                "bogus": "value",
            }
        )


def test_channel_limits_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ChannelLimits(max_voltage=0, max_current=1.0)
    with pytest.raises(ValidationError):
        ChannelLimits(max_voltage=10.0, max_current=-1.0)


def test_channel_limits_round_trip() -> None:
    limits = ChannelLimits(max_voltage=20.0, max_current=0.1)
    payload = limits.model_dump()
    assert payload == {"max_voltage": 20.0, "max_current": 0.1}
    assert ChannelLimits.model_validate(payload) == limits
