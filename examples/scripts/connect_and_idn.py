"""Discover, connect, query IDN, and optionally run a small sweep.

Usage::

    python examples/scripts/connect_and_idn.py
    python examples/scripts/connect_and_idn.py --resource 'GPIB0::17::INSTR'
    python examples/scripts/connect_and_idn.py --mock
    python examples/scripts/connect_and_idn.py --mock --sweep

Headless smoke test for M0 steps 2 and 3+4: exercises discovery, connect,
``*IDN?``, and (with ``--sweep``) the engine + driver measurement path.
"""
from __future__ import annotations

import argparse
import logging
import sys

from paramctl.driver import (
    AnalyzerDriver,
    CommunicationError,
    FlexDriver,
    MockDriver,
    list_resources,
)
from paramctl.engine import SampleReady, SweepCompleted, SweepFailed, run_sweep
from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepMeasurement,
    SweepRange,
)


def _pick_resource(provided: str | None) -> str | None:
    if provided is not None:
        return provided

    resources = list_resources()
    if not resources:
        print("No VISA resources discovered. Pass --mock to use the synthetic driver.")
        return None

    print("Discovered VISA resources:")
    for index, resource in enumerate(resources):
        print(f"  [{index}] {resource}")

    while True:
        choice = input(f"Select resource [0-{len(resources) - 1}] (or 'q' to quit): ").strip()
        if choice.lower() == "q":
            return None
        try:
            return resources[int(choice)]
        except (ValueError, IndexError):
            print("Invalid choice; try again.")


def _id_vds_setup() -> Setup:
    return Setup(
        name="Example ID-VDS sweep at VGS=1.5 V",
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


def _print_sweep(driver: AnalyzerDriver) -> int:
    setup = _id_vds_setup()
    print(f"Running sweep: {setup.name}")
    print(f"{'idx':>4}  {'V_DS [V]':>10}  {'I_D [A]':>14}  {'I_G [A]':>14}")
    for event in run_sweep(driver, setup):
        if isinstance(event, SampleReady):
            sample = event.sample
            id_a = sample.readings.get(ChannelId.SMU1, float("nan"))
            ig_a = sample.readings.get(ChannelId.SMU2, float("nan"))
            print(f"{sample.index:>4}  {sample.var1_value:>10.4f}  {id_a:>14.4e}  {ig_a:>14.4e}")
        elif isinstance(event, SweepCompleted):
            print(
                f"-- completed: {event.sample_count} samples, "
                f"aborted={event.aborted}"
            )
            return 0
        elif isinstance(event, SweepFailed):
            print(f"-- failed: {event.exception!r}", file=sys.stderr)
            return 3
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resource",
        help="VISA resource string. If omitted, lists discovered resources interactively.",
    )
    parser.add_argument(
        "--mock", action="store_true", help="Use MockDriver instead of opening a VISA resource."
    )
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="After IDN, run a 21-point ID-VDS sweep and print the samples.",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable DEBUG-level logging."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    driver: AnalyzerDriver
    if args.mock:
        driver = MockDriver(inter_sample_delay_s=0.02)
    else:
        resource = _pick_resource(args.resource)
        if resource is None:
            return 1
        driver = FlexDriver(resource)

    try:
        with driver:
            print(f"*IDN? -> {driver.idn()}")
            if args.sweep:
                return _print_sweep(driver)
    except CommunicationError as exc:
        print(f"Communication error: {exc}", file=sys.stderr)
        return 2
    except NotImplementedError as exc:
        print(f"Not yet implemented: {exc}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
