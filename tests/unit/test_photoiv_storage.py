"""Unit tests for per-curve photo-IV storage."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    IlluminationSequence,
    IlluminationStep,
    PhotoIvCampaign,
    Sample,
    Setup,
    SweepMeasurement,
    SweepRange,
)
from paramctl.persistence import (
    photoiv_filename,
    read_run_csv,
    write_campaign_curve,
)


def _campaign() -> PhotoIvCampaign:
    setup = Setup(
        name="diode IV",
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10e-3,
            ),
        ],
        measurement=SweepMeasurement(var1=SweepRange(start=-1.0, stop=1.0, points=3)),
    )
    return PhotoIvCampaign(
        base_setup=setup,
        illumination=IlluminationSequence.intensity_series(385.0, [50.0]),
        device_id="dev42",
        notes="bench test",
    )


def _samples() -> list[Sample]:
    return [
        Sample(index=i, var1_value=v, readings={ChannelId.SMU1: 1e-6 * (i + 1)})
        for i, v in enumerate((-1.0, 0.0, 1.0))
    ]


def test_filename_encodes_device_and_label() -> None:
    campaign = _campaign()
    step = IlluminationStep(label="385nm_50pct", wavelength_nm=385.0, intensity_pct=50.0)
    ts = dt.datetime(2026, 6, 10, 14, 22, 33)
    name = photoiv_filename(campaign, step, ts)
    assert name == "IV_dev42_385nm_50pct_20260610_142233.csv"


def test_write_campaign_curve_roundtrips_and_carries_illumination(tmp_path: Path) -> None:
    campaign = _campaign()
    step = IlluminationStep(label="385nm_50pct", wavelength_nm=385.0, intensity_pct=50.0)
    samples = _samples()

    path = write_campaign_curve(
        tmp_path,
        campaign,
        step,
        samples,
        timestamp=dt.datetime(2026, 6, 10, 14, 22, 33),
        led_current_ma=500.0,
    )
    assert path.exists()
    assert path.name == "IV_dev42_385nm_50pct_20260610_142233.csv"

    text = path.read_text()
    assert "# illumination_label: 385nm_50pct" in text
    assert "# wavelength_nm: 385.0" in text
    assert "# intensity_pct: 50.0" in text
    assert "# is_dark: False" in text
    assert "# led_current_ma: 500.0" in text
    assert "# campaign_device_id: dev42" in text

    # The standard trace reader still recovers setup + samples (extra header
    # comment lines are ignored), so existing analysis tooling is unaffected.
    setup, recovered = read_run_csv(path)
    assert setup.name == "diode IV"
    assert len(recovered) == 3
    assert recovered[0].readings[ChannelId.SMU1] == 1e-6


def test_filename_and_metadata_include_curve_label(tmp_path: Path) -> None:
    campaign = _campaign()
    step = IlluminationStep(label="385nm_50pct", wavelength_nm=385.0, intensity_pct=50.0)
    ts = dt.datetime(2026, 6, 10, 14, 22, 33)

    name = photoiv_filename(campaign, step, ts, curve_label="0to+7V")
    assert name == "IV_dev42_385nm_50pct_0to+7V_20260610_142233.csv"

    path = write_campaign_curve(
        tmp_path, campaign, step, _samples(), curve_label="0to-7V", timestamp=ts
    )
    assert "0to-7V" in path.name
    assert "# curve_range: 0to-7V" in path.read_text()


def test_dark_curve_metadata_marks_dark(tmp_path: Path) -> None:
    campaign = _campaign()
    step = IlluminationStep(label="dark_pre")
    path = write_campaign_curve(tmp_path, campaign, step, _samples())
    text = path.read_text()
    assert "# is_dark: True" in text
    assert "# wavelength_nm: dark" in text
