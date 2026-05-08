"""Tests for YAML save/load of ``Setup`` instances and the migration spine."""
from __future__ import annotations

import pytest

from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelLimits,
    ChannelMode,
    Setup,
    SweepDirection,
    SweepMeasurement,
    SweepRange,
    SweepScale,
)
from paramctl.persistence import (
    SetupFileError,
    dump_setup_yaml,
    load_setup,
    load_setup_yaml,
    save_setup,
)


def _setup() -> Setup:
    return Setup(
        name="ID-VDS at VGS=1.5 V",
        notes="Test fixture used by persistence tests.",
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
        safety_ceilings={
            ChannelId.SMU1: ChannelLimits(max_voltage=20.0, max_current=0.1),
        },
        resource_string="GPIB0::15::INSTR",
    )


def test_dump_yaml_round_trips() -> None:
    setup = _setup()
    text = dump_setup_yaml(setup)
    rebuilt = load_setup_yaml(text)
    assert rebuilt == setup


def test_dump_yaml_is_human_readable() -> None:
    setup = _setup()
    text = dump_setup_yaml(setup)
    # Plain mappings, no Python-specific tags, no obscure node types.
    assert "schema_version: 1" in text
    assert "name: ID-VDS at VGS=1.5 V" in text
    assert "SMU1" in text
    assert "!!python/" not in text


def test_save_and_load_round_trip(tmp_path) -> None:
    setup = _setup()
    path = tmp_path / "setup.yaml"
    save_setup(path, setup)
    rebuilt = load_setup(path)
    assert rebuilt == setup


def test_load_setup_handles_log_sweep(tmp_path) -> None:
    """Enums (SweepScale, SweepDirection) must round-trip as their string values."""
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
                start=1e-3,
                stop=1.0,
                points=13,
                scale=SweepScale.LOG10,
                direction=SweepDirection.DOUBLE,
            )
        ),
    )
    path = tmp_path / "log.yaml"
    save_setup(path, setup)
    rebuilt = load_setup(path)
    assert rebuilt.measurement.var1.scale is SweepScale.LOG10  # type: ignore[union-attr]
    assert rebuilt.measurement.var1.direction is SweepDirection.DOUBLE  # type: ignore[union-attr]


def test_load_yaml_rejects_non_mapping() -> None:
    with pytest.raises(SetupFileError, match="must be a mapping"):
        load_setup_yaml("- not\n- a\n- mapping\n")


def test_load_yaml_rejects_missing_schema_version() -> None:
    with pytest.raises(SetupFileError, match="schema_version"):
        load_setup_yaml("name: foo\n")


def test_load_yaml_rejects_unknown_future_schema_version() -> None:
    """A v2 file with no migration registered must surface clearly."""
    text = "schema_version: 99\nname: future setup\nchannels: []\n"
    with pytest.raises(SetupFileError, match="cannot migrate"):
        load_setup_yaml(text)


def test_load_yaml_rejects_garbage_payload() -> None:
    """A v1 file that fails Pydantic validation surfaces as SetupFileError."""
    text = (
        "schema_version: 1\n"
        "channels: []\n"
        "measurement:\n"
        "  kind: sweep\n"
        "  var1: { start: 0, stop: 1, points: 11 }\n"
    )
    with pytest.raises(SetupFileError, match="failed validation"):
        load_setup_yaml(text)


def test_load_setup_io_error(tmp_path) -> None:
    missing = tmp_path / "does_not_exist.yaml"
    with pytest.raises(SetupFileError, match="could not read"):
        load_setup(missing)
