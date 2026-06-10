"""Unit tests for the hardware-free ``MockLightSource``."""
from __future__ import annotations

import pytest

from paramctl.light import (
    DEFAULT_WAVELENGTHS_NM,
    MockLightSource,
    NotConnectedError,
    UnknownWavelengthError,
)


def test_default_wiring_has_eight_channels() -> None:
    led = MockLightSource()
    assert led.wavelengths() == DEFAULT_WAVELENGTHS_NM
    assert len(led.wavelengths()) == 8
    assert led.channel_of(385.0) == 7
    assert led.channel_of(850.0) == 0


def test_set_intensity_tracks_active_channel_and_records_calls() -> None:
    led = MockLightSource()
    led.connect()
    led.set_intensity(385.0, 50.0)
    assert led.active == {385.0: 50.0}
    led.set_intensity(530.0, 80.0)
    assert led.active == {530.0: 80.0}  # only one channel lit at a time
    led.all_off()
    assert led.active == {}

    names = [c.name for c in led.calls]
    assert names == ["connect", "set_intensity", "set_intensity", "all_off"]


def test_set_intensity_before_connect_raises() -> None:
    led = MockLightSource()
    with pytest.raises(NotConnectedError):
        led.set_intensity(385.0, 50.0)


def test_unknown_wavelength_raises() -> None:
    led = MockLightSource()
    led.connect()
    with pytest.raises(UnknownWavelengthError):
        led.set_intensity(123.0, 10.0)
    with pytest.raises(UnknownWavelengthError):
        led.channel_of(123.0)


def test_current_ma_for_uses_effective_full_scale() -> None:
    led = MockLightSource()
    assert led.current_ma_for(385.0, 50.0) == pytest.approx(500.0)
    # 590 nm is software-limited to 700 mA full-scale.
    assert led.current_ma_for(590.0, 100.0) == pytest.approx(700.0)
    assert led.current_ma_for(123.0, 50.0) is None


def test_predicted_power_none_without_model_then_linear_with_model() -> None:
    assert MockLightSource().predicted_power_mw(385.0, 50.0) is None
    led = MockLightSource(power_model_mw={385.0: 10.0})
    assert led.predicted_power_mw(385.0, 50.0) == pytest.approx(5.0)
    assert led.predicted_power_mw(530.0, 50.0) is None  # uncalibrated channel


def test_context_manager_connects_and_disconnects() -> None:
    led = MockLightSource()
    with led as src:
        assert src.is_connected is True
    assert led.is_connected is False
