"""Launcher for the photo-IV campaign GUI (``paramctl-photoiv``).

Instrument selection happens **inside the GUI** — the "Instruments" panel
picks the analyzer (mock or a VISA resource, with discovery + an explicit
Connect/IDN step) and the light source (PXI FPGA bitfile or mock). All CLI
flags here are just pre-fills for that panel, the same convention as
``mfia-cf``::

    paramctl-photoiv                          # blank GUI; pick instruments inside
    paramctl-photoiv --mock                   # pre-select + auto-connect mocks
    paramctl-photoiv --resource GPIB0::17::INSTR --led-bitfile /path/led.lvbitx
"""
from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtWidgets import QApplication

from ..models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepMeasurement,
    SweepRange,
)
from .photoiv_window import PhotoIvWindow

logger = logging.getLogger(__name__)


def _default_setup() -> Setup:
    """A symmetric diode-style IV sweep on SMU1, as the base measurement."""
    return Setup(
        name="IV sweep",
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10e-3,
                label="Device",
            ),
            ChannelConfig(
                channel_id=ChannelId.SMU2,
                mode=ChannelMode.COMMON,
                function=ChannelFunction.CONST,
                label="Common",
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=-1.0, stop=1.0, points=41)
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mock", action="store_true",
        help="Pre-select and auto-connect the mock analyzer + mock light.",
    )
    parser.add_argument(
        "--resource", default=None,
        help="Pre-fill the analyzer VISA resource (e.g. 'GPIB0::17::INSTR').",
    )
    parser.add_argument(
        "--led-mock", action="store_true",
        help="Pre-select the mock light source.",
    )
    parser.add_argument(
        "--led-bitfile", default=None,
        help="Pre-fill the PXI-7853R .lvbitx bitfile path.",
    )
    parser.add_argument(
        "--led-resource", default="RIO0", help="Pre-fill the NI-RIO resource name."
    )
    parser.add_argument(
        "--led-use-cal", action="store_true",
        help="Pre-check 'apply power calibration' (equal %% = equal power).",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="DEBUG logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])

    window = PhotoIvWindow(
        _default_setup(),
        preselect_mock=args.mock,
        resource=args.resource,
        led_mock=args.led_mock,
        led_bitfile=args.led_bitfile,
        led_resource=args.led_resource,
        led_use_cal=args.led_use_cal,
    )
    window.resize(1280, 820)
    window.show()
    return app.exec()


__all__ = ["main"]
