"""Tests for CSV trace export/import."""
from __future__ import annotations

import pytest

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
from paramctl.persistence import (
    TraceFileError,
    dump_run_csv,
    parse_run_csv,
    read_run_csv,
    write_run_csv,
)


def _setup() -> Setup:
    return Setup(
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
            var1=SweepRange(start=0.0, stop=2.0, points=5)
        ),
    )


def _samples() -> list[Sample]:
    return [
        Sample(
            index=i,
            var1_value=i * 0.5,
            readings={ChannelId.SMU1: 1e-6 * (i + 1)},
            timestamp=i * 0.05,
            compliance_hit=(i == 3),
        )
        for i in range(5)
    ]


def test_dump_run_csv_contains_setup_and_data() -> None:
    text = dump_run_csv(_setup(), _samples())
    assert text.startswith("# paramctl trace export\n")
    assert "# ----- setup begin -----" in text
    assert "# ----- setup end -----" in text
    assert "schema_version: 1" in text
    assert "ID-VDS at VGS=1.5 V" in text
    # Data section
    assert "index,var1_value,SMU1,compliance_hit,timestamp" in text
    assert "0,0.0,1e-06,False,0.0" in text


def test_round_trip_preserves_setup_and_samples() -> None:
    setup = _setup()
    samples = _samples()
    text = dump_run_csv(setup, samples)
    rebuilt_setup, rebuilt_samples = parse_run_csv(text)

    assert rebuilt_setup == setup
    assert len(rebuilt_samples) == len(samples)
    for got, want in zip(rebuilt_samples, samples, strict=True):
        assert got.index == want.index
        assert got.var1_value == pytest.approx(want.var1_value)
        assert got.compliance_hit == want.compliance_hit
        assert got.timestamp == pytest.approx(want.timestamp)
        assert got.readings == want.readings


def test_write_and_read_via_filesystem(tmp_path) -> None:
    path = tmp_path / "trace.csv"
    setup = _setup()
    samples = _samples()
    write_run_csv(path, setup, samples)
    rebuilt_setup, rebuilt_samples = read_run_csv(path)
    assert rebuilt_setup == setup
    assert len(rebuilt_samples) == len(samples)


def test_compliance_flag_round_trips() -> None:
    text = dump_run_csv(_setup(), _samples())
    _, samples = parse_run_csv(text)
    flags = [s.compliance_hit for s in samples]
    assert flags == [False, False, False, True, False]


def test_parse_rejects_missing_setup_block() -> None:
    bad = "index,var1_value,SMU1,compliance_hit,timestamp\n0,0.0,1e-6,False,0.0\n"
    with pytest.raises(TraceFileError, match="missing the embedded setup"):
        parse_run_csv(bad)


def test_parse_rejects_missing_csv_body() -> None:
    setup = _setup()
    text = dump_run_csv(setup, _samples())
    # Strip everything after the setup-end marker.
    head = text.split("# ----- setup end -----")[0] + "# ----- setup end -----\n"
    with pytest.raises(TraceFileError, match="missing the header row|no CSV body"):
        parse_run_csv(head)


def test_csv_header_lists_all_measured_channels() -> None:
    samples = [
        Sample(
            index=0,
            var1_value=0.0,
            readings={ChannelId.SMU1: 1e-6, ChannelId.SMU3: 2e-6},
        ),
    ]
    text = dump_run_csv(_setup(), samples)
    header = next(
        line for line in text.splitlines()
        if line.startswith("index,")
    )
    assert "SMU1" in header
    assert "SMU3" in header


def test_round_trip_handles_log_sweep_setup(tmp_path) -> None:
    from paramctl.models import SweepScale

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
                start=1e-3, stop=1.0, points=4, scale=SweepScale.LOG10
            )
        ),
    )
    samples = [
        Sample(index=i, var1_value=10 ** (-3 + i), readings={ChannelId.SMU1: 1e-9})
        for i in range(4)
    ]
    path = tmp_path / "log.csv"
    write_run_csv(path, setup, samples)
    rebuilt_setup, rebuilt_samples = read_run_csv(path)
    assert rebuilt_setup == setup
    assert len(rebuilt_samples) == 4
