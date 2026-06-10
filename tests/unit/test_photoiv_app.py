"""Unit tests for the photo-IV window's instrument pre-fill behaviour."""
from __future__ import annotations

from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepMeasurement,
    SweepRange,
)
from paramctl.ui.photoiv_window import PhotoIvWindow


def _setup() -> Setup:
    return Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10e-3,
            ),
        ],
        measurement=SweepMeasurement(var1=SweepRange(start=-1.0, stop=1.0, points=5)),
    )


def test_blank_launch_defaults_to_pxi_light_and_no_connection(qtbot) -> None:
    win = PhotoIvWindow(_setup())
    qtbot.addWidget(win)
    assert win._driver is None
    assert win._light_combo.currentText() == "PXI FPGA LED source"
    assert win._analyzer_status.text() == "not connected"


def test_resource_and_bitfile_prefills_land_in_fields(qtbot) -> None:
    win = PhotoIvWindow(
        _setup(),
        resource="GPIB0::17::INSTR",
        led_bitfile="/path/to/led.lvbitx",
        led_resource="RIO1",
        led_use_cal=True,
    )
    qtbot.addWidget(win)
    assert win._resource_combo.currentText() == "GPIB0::17::INSTR"
    assert win._bitfile_edit.text() == "/path/to/led.lvbitx"
    assert win._led_resource_edit.text() == "RIO1"
    assert win._use_cal_check.isChecked()
    # Pre-filling a real resource must NOT auto-connect (explicit IDN step).
    assert win._driver is None


def test_led_mock_prefill_selects_mock_light(qtbot) -> None:
    win = PhotoIvWindow(_setup(), led_mock=True)
    qtbot.addWidget(win)
    assert win._light_combo.currentText() == "Mock light"
    assert win._driver is None  # analyzer untouched
