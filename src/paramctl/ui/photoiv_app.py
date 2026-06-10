"""Launcher for the photo-IV campaign GUI (``paramctl-photoiv``).

Builds an analyzer driver and an LED light source from the CLI flags (mock by
default-friendly, real hardware when asked), a default IV sweep, and shows the
campaign window. The analyzer connection is owned here for the window's
lifetime; the light source is connected/disconnected per campaign by the
engine, so nothing here needs ``led_driver`` installed unless real LED
hardware is selected.
"""
from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtWidgets import QApplication

from ..driver import (
    AnalyzerDriver,
    CommunicationError,
    FlexDriver,
    MockDriver,
    list_resources,
)
from ..light.base import LightSource
from ..light.mock import MockLightSource
from ..light.pxi import PxiLightSource
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


def _build_driver(args: argparse.Namespace) -> AnalyzerDriver | None:
    if args.mock:
        return MockDriver(inter_sample_delay_s=0.02)
    resource = args.resource
    if resource is None:
        resources = list_resources()
        if not resources:
            print(
                "No VISA resources discovered. Pass --mock for the synthetic "
                "driver or --resource '<visa-string>' for a specific instrument.",
                file=sys.stderr,
            )
            return None
        if len(resources) == 1:
            resource = resources[0]
            print(f"Auto-selected the only VISA resource: {resource}")
        else:
            print("Multiple VISA resources discovered; pick one with --resource:")
            for r in resources:
                print(f"  {r}")
            return None
    return FlexDriver(resource)


def _build_light(args: argparse.Namespace) -> LightSource:
    if args.mock or args.led_mock:
        return MockLightSource()
    return PxiLightSource(
        bitfile=args.led_bitfile,
        resource=args.led_resource,
        use_cal=args.led_use_cal,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mock", action="store_true",
        help="Use the synthetic analyzer AND the mock light source.",
    )
    parser.add_argument(
        "--resource", default=None,
        help="VISA resource string for the analyzer (e.g. 'GPIB0::17::INSTR').",
    )
    parser.add_argument(
        "--led-mock", action="store_true",
        help="Use the mock light source with a real analyzer.",
    )
    parser.add_argument(
        "--led-bitfile", default=None,
        help="PXI-7853R .lvbitx bitfile. Omit to use the led_driver mock backend.",
    )
    parser.add_argument("--led-resource", default="RIO0", help="NI-RIO resource name.")
    parser.add_argument(
        "--led-use-cal", action="store_true",
        help="Apply the led_driver power calibration (equal %% = equal power).",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="DEBUG logging.")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])

    driver = _build_driver(args)
    if driver is None:
        return 1
    light = _build_light(args)

    try:
        driver.connect()
    except CommunicationError as exc:
        print(f"Failed to connect to analyzer: {exc}", file=sys.stderr)
        return 2

    window = PhotoIvWindow(driver, light, _default_setup())
    window.resize(1280, 760)
    window.show()

    try:
        return app.exec()
    finally:
        try:
            driver.disconnect()
        except Exception:
            logger.exception("photoiv_app: driver.disconnect() raised at shutdown")


__all__ = ["main"]
