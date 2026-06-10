"""Unit tests for the :class:`PhotoIvCampaign` model."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    IlluminationSequence,
    PhotoIvCampaign,
    SamplingMeasurement,
    Setup,
    SweepMeasurement,
    SweepRange,
)


def _iv_setup() -> Setup:
    return Setup(
        name="diode IV",
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10e-3,
            ),
        ],
        measurement=SweepMeasurement(var1=SweepRange(start=-1.0, stop=1.0, points=21)),
    )


def _sampling_setup() -> Setup:
    return Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.CONST,
                source_value=0.5,
                compliance=10e-3,
            ),
        ],
        measurement=SamplingMeasurement(interval=0.1, points=10),
    )


def test_campaign_accepts_sweep_base() -> None:
    campaign = PhotoIvCampaign(
        base_setup=_iv_setup(),
        illumination=IlluminationSequence.intensity_series(385.0, [50.0, 100.0]),
        inter_step_delay_s=2.0,
        device_id="dev42",
    )
    assert campaign.device_id == "dev42"
    assert len(campaign.illumination) == 1 + 2 * 2


def test_campaign_rejects_non_sweep_base() -> None:
    with pytest.raises(ValidationError):
        PhotoIvCampaign(
            base_setup=_sampling_setup(),
            illumination=IlluminationSequence.intensity_series(385.0, [50.0]),
        )


def test_inter_step_delay_must_be_non_negative() -> None:
    with pytest.raises(ValidationError):
        PhotoIvCampaign(
            base_setup=_iv_setup(),
            illumination=IlluminationSequence.intensity_series(385.0, [50.0]),
            inter_step_delay_s=-1.0,
        )


def test_no_sweep_ranges_gives_single_unlabelled_setup() -> None:
    campaign = PhotoIvCampaign(
        base_setup=_iv_setup(),
        illumination=IlluminationSequence.intensity_series(385.0, [100.0]),
    )
    pairs = campaign.setups_for_step()
    assert len(pairs) == 1
    label, setup = pairs[0]
    assert label == ""
    assert setup is campaign.base_setup


def test_dual_sweep_ranges_override_var1_and_label_each_curve() -> None:
    ranges = [
        SweepRange(start=0.0, stop=7.0, points=11),
        SweepRange(start=0.0, stop=-7.0, points=11),
    ]
    campaign = PhotoIvCampaign(
        base_setup=_iv_setup(),
        illumination=IlluminationSequence.intensity_series(385.0, [100.0]),
        sweep_ranges=ranges,
    )
    pairs = campaign.setups_for_step()
    assert [label for label, _ in pairs] == ["0to+7V", "0to-7V"]
    pos, neg = pairs[0][1], pairs[1][1]
    assert isinstance(pos.measurement, SweepMeasurement)
    assert isinstance(neg.measurement, SweepMeasurement)
    assert pos.measurement.var1.stop == 7.0
    assert neg.measurement.var1.stop == -7.0
    # Channels / compliance carry over untouched from the base setup.
    assert pos.channels == campaign.base_setup.channels


def test_empty_sweep_ranges_rejected() -> None:
    with pytest.raises(ValidationError):
        PhotoIvCampaign(
            base_setup=_iv_setup(),
            illumination=IlluminationSequence.intensity_series(385.0, [100.0]),
            sweep_ranges=[],
        )
