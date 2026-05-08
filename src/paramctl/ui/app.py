"""Launcher: build a default setup, pick a driver, show the main window."""
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
from ..models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepMeasurement,
    SweepRange,
)
from .main_window import MainWindow


def _default_setup() -> Setup:
    return Setup(
        name="ID-VDS at VGS = 1.5 V",
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
    )


def _build_driver(args: argparse.Namespace) -> AnalyzerDriver | None:
    if args.mock:
        return MockDriver(inter_sample_delay_s=0.05)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mock", action="store_true", help="Use the synthetic MockDriver."
    )
    parser.add_argument(
        "--resource",
        default=None,
        help="VISA resource string (e.g. 'GPIB0::15::INSTR'). If omitted, "
        "the only discovered resource is used; if there are several, you must pick.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable DEBUG logging."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])

    driver = _build_driver(args)
    if driver is None:
        return 1

    try:
        driver.connect()
    except CommunicationError as exc:
        print(f"Failed to connect: {exc}", file=sys.stderr)
        return 2

    setup = _default_setup()
    window = MainWindow(driver, setup)
    window.resize(900, 600)
    window.show()

    try:
        return app.exec()
    finally:
        try:
            driver.disconnect()
        except Exception:
            logging.getLogger(__name__).exception("driver.disconnect() raised at shutdown")


__all__ = ["main"]
