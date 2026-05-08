"""Unit tests for FLEX command builder and FMT 1 response parser.

These exercise ``flex_protocol`` directly with no PyVISA / no instrument
involvement. The wire-level FlexDriver is tested against real hardware.
"""
from __future__ import annotations

import pytest

from paramctl.driver.flex_protocol import (
    FlexProtocolError,
    build_setup_commands,
    channel_number,
    expected_value_count,
    parse_field,
    parse_response,
)
from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SpotMeasurement,
    SweepDirection,
    SweepMeasurement,
    SweepRange,
    SweepScale,
)


@pytest.mark.parametrize(
    "channel,number",
    [
        (ChannelId.SMU1, 1),
        (ChannelId.SMU2, 2),
        (ChannelId.SMU3, 3),
        (ChannelId.SMU4, 4),
    ],
)
def test_channel_number_for_smus(channel: ChannelId, number: int) -> None:
    assert channel_number(channel) == number


@pytest.mark.parametrize("channel", [ChannelId.VSU1, ChannelId.VMU1, ChannelId.GNDU])
def test_channel_number_rejects_unsupported(channel: ChannelId) -> None:
    with pytest.raises(FlexProtocolError, match="does not yet support"):
        channel_number(channel)


def test_expected_value_count_single_direction() -> None:
    sweep = SweepMeasurement(var1=SweepRange(start=0.0, stop=1.0, points=21))
    assert expected_value_count(sweep) == 42  # 21 points * 2 fields


def test_expected_value_count_double_direction() -> None:
    sweep = SweepMeasurement(
        var1=SweepRange(
            start=0.0, stop=1.0, points=11, direction=SweepDirection.DOUBLE
        )
    )
    assert expected_value_count(sweep) == 42  # (2*11 - 1) * 2


def _smu_var1(compliance: float | None = 1e-3) -> ChannelConfig:
    return ChannelConfig(
        channel_id=ChannelId.SMU1,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.VAR1,
        compliance=compliance,
    )


def _smu2_const(value: float = 1.5) -> ChannelConfig:
    return ChannelConfig(
        channel_id=ChannelId.SMU2,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.CONST,
        source_value=value,
        compliance=1e-3,
    )


def _basic_setup() -> Setup:
    return Setup(
        channels=[_smu_var1(), _smu2_const()],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=2.0, points=21)
        ),
    )


def test_build_setup_commands_emits_us_and_fmt_first() -> None:
    cmds = build_setup_commands(_basic_setup())
    assert cmds[0] == "US"
    assert cmds[1] == "FMT 1,1"


def test_build_setup_commands_enables_all_active_channels() -> None:
    cmds = build_setup_commands(_basic_setup())
    cn_cmd = next(c for c in cmds if c.startswith("CN "))
    nums = sorted(cn_cmd[3:].split(","))
    assert nums == ["1", "2"]


def test_build_setup_commands_wv_for_voltage_var1() -> None:
    cmds = build_setup_commands(_basic_setup())
    wv = next(c for c in cmds if c.startswith("WV "))
    parts = wv[3:].split(",")
    assert parts[0] == "1"          # SMU1
    assert parts[1] == "1"          # linear single
    assert parts[2] == "0"          # auto range
    assert float(parts[3]) == 0.0
    assert float(parts[4]) == 2.0
    assert parts[5] == "21"
    assert float(parts[6]) == 1e-3  # compliance


def test_build_setup_commands_wi_for_current_var1() -> None:
    setup = Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.I_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=2.0,
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=1e-3, points=11)
        ),
    )
    cmds = build_setup_commands(setup)
    assert any(c.startswith("WI ") for c in cmds)
    assert not any(c.startswith("WV ") for c in cmds)


def test_build_setup_commands_double_direction_uses_mode_2() -> None:
    setup = Setup(
        channels=[_smu_var1(), _smu2_const()],
        measurement=SweepMeasurement(
            var1=SweepRange(
                start=0.0, stop=1.0, points=11, direction=SweepDirection.DOUBLE
            )
        ),
    )
    wv = next(c for c in build_setup_commands(setup) if c.startswith("WV "))
    assert wv.split(",")[1] == "2"


def test_build_setup_commands_log_uses_mode_3() -> None:
    setup = Setup(
        channels=[_smu_var1()],
        measurement=SweepMeasurement(
            var1=SweepRange(
                start=1e-3, stop=1.0, points=13, scale=SweepScale.LOG10
            )
        ),
    )
    wv = next(c for c in build_setup_commands(setup) if c.startswith("WV "))
    assert wv.split(",")[1] == "3"


def test_build_setup_commands_const_dv_for_voltage_source() -> None:
    cmds = build_setup_commands(_basic_setup())
    dv = next(c for c in cmds if c.startswith("DV "))
    parts = dv[3:].split(",")
    assert parts[0] == "2"            # SMU2
    assert parts[1] == "0"            # auto
    assert float(parts[2]) == 1.5     # source value
    assert float(parts[3]) == 1e-3    # compliance


def test_build_setup_commands_includes_wt_and_mm() -> None:
    cmds = build_setup_commands(_basic_setup())
    assert any(c.startswith("WT ") for c in cmds)
    mm = next(c for c in cmds if c.startswith("MM "))
    assert mm == "MM 2,1"  # mode 2 = staircase, measure on SMU1


def test_build_setup_commands_rejects_non_sweep() -> None:
    setup = Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.CONST,
                compliance=1e-3,
            ),
        ],
        measurement=SpotMeasurement(),
    )
    with pytest.raises(FlexProtocolError, match="only supports sweep"):
        build_setup_commands(setup)


def test_build_setup_commands_rejects_non_smu() -> None:
    setup = Setup(
        channels=[
            _smu_var1(),
            ChannelConfig(
                channel_id=ChannelId.VSU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.CONST,
                source_value=0.5,
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=1.0, points=5)
        ),
    )
    with pytest.raises(FlexProtocolError, match="only supports SMU"):
        build_setup_commands(setup)


# --- response parser ---------------------------------------------------------

# Real captured response from the 4155B (probe on 2026-05-08, open-circuit
# 6-point V-sweep on SMU1 from 0 to 0.5 V). Used as ground truth for the parser.
_REAL_RESPONSE = (
    "000AI+7.500000E-14,  WAv+0.000000E+00,"
    "000AI+6.900000E-14,  WAv+1.000000E-01,"
    "000AI+2.600000E-14,  WAv+2.000000E-01,"
    "000AI+1.400000E-14,  WAv+3.000000E-01,"
    "000AI+5.700000E-14,  WAv+4.000000E-01,"
    "000AI-8.100000E-14,  EAv+5.000000E-01"
)


def test_parse_field_decodes_measurement() -> None:
    f = parse_field("000AI+7.500000E-14")
    assert f.channel is ChannelId.SMU1
    assert f.is_source is False
    assert f.is_voltage is False  # current
    assert f.value == pytest.approx(7.5e-14)


def test_parse_field_decodes_source_voltage() -> None:
    f = parse_field("  WAv+1.000000E-01")
    assert f.channel is ChannelId.SMU1
    assert f.is_source is True
    assert f.is_voltage is True
    assert f.value == pytest.approx(0.1)


def test_parse_field_rejects_wrong_length() -> None:
    with pytest.raises(FlexProtocolError, match="18-char"):
        parse_field("too short")


def test_parse_field_rejects_unknown_channel() -> None:
    with pytest.raises(FlexProtocolError, match="channel letter"):
        parse_field("000ZI+1.000000E-03")


def test_parse_response_handles_real_capture() -> None:
    fields = parse_response(_REAL_RESPONSE)
    assert len(fields) == 12

    sources = [f for f in fields if f.is_source]
    measurements = [f for f in fields if not f.is_source]
    assert len(sources) == 6
    assert len(measurements) == 6

    expected_v = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    actual_v = [f.value for f in sources]
    for got, want in zip(actual_v, expected_v, strict=True):
        assert got == pytest.approx(want)

    assert all(f.channel is ChannelId.SMU1 for f in fields)


def test_parse_field_status_codes_round_trip() -> None:
    # Final-point status differs from intermediate (E vs W in real captures).
    intermediate = parse_field("  WAv+1.000000E-01")
    last_point = parse_field("  EAv+5.000000E-01")
    assert intermediate.status == "  W"
    assert last_point.status == "  E"


def test_parse_field_compliance_hit_flag_for_normal_status() -> None:
    # Real captured normal-measurement field; status "000" -> no compliance.
    field = parse_field("000AI+7.500000E-14")
    assert field.compliance_hit is False


def test_parse_field_compliance_hit_flag_for_compliance_status() -> None:
    # Real captured compliance-reached field; status "008" -> compliance set.
    # Captured from a 4155B forcing 1 mA into open circuit with Vcomp=2 V.
    field = parse_field("008AV+2.000028E+00")
    assert field.compliance_hit is True
    assert field.value == pytest.approx(2.000028)


def test_parse_field_compliance_hit_false_for_source_data() -> None:
    """Source-data fields use the status area for sweep markers, never
    encode compliance there. ``W`` and ``E`` markers must not be flagged
    as compliance hits.
    """
    intermediate = parse_field("  WAv+1.000000E-01")
    last_point = parse_field("  EAv+5.000000E-01")
    assert intermediate.compliance_hit is False
    assert last_point.compliance_hit is False
