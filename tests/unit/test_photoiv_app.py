"""Unit tests for the photo-IV launcher's driver/light selection logic."""
from __future__ import annotations

import argparse

from paramctl.light import MockLightSource, PxiLightSource
from paramctl.ui.photoiv_app import _build_light


def _ns(**overrides: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "mock": False,
        "resource": None,
        "led_mock": False,
        "led_bitfile": None,
        "led_resource": "RIO0",
        "led_use_cal": False,
        "verbose": False,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_mock_flag_selects_mock_light() -> None:
    assert isinstance(_build_light(_ns(mock=True)), MockLightSource)


def test_led_mock_flag_selects_mock_light() -> None:
    assert isinstance(_build_light(_ns(led_mock=True)), MockLightSource)


def test_real_run_without_bitfile_is_refused(capsys) -> None:
    # led_driver would silently fall back to its own mock backend — the
    # launcher must refuse instead so an "illuminated" campaign can't run dark.
    assert _build_light(_ns()) is None
    err = capsys.readouterr().err
    assert "--led-bitfile" in err and "--led-mock" in err


def test_bitfile_selects_real_pxi_source() -> None:
    light = _build_light(_ns(led_bitfile="/path/to/led.lvbitx"))
    assert isinstance(light, PxiLightSource)
    assert light.bitfile == "/path/to/led.lvbitx"
