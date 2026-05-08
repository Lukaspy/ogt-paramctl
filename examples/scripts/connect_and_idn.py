"""Discover VISA resources, let the user pick one, connect, print ``*IDN?``.

Usage::

    python examples/scripts/connect_and_idn.py
    python examples/scripts/connect_and_idn.py --resource 'GPIB0::17::INSTR'
    python examples/scripts/connect_and_idn.py --mock

This is a headless smoke test for the M0 step-2 vertical slice. It exercises
``list_resources()``, ``FlexDriver``, and ``MockDriver`` without involving
the GUI, so it runs over SSH and inside CI.
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


def _pick_resource(provided: str | None) -> str | None:
    """Return the resource string to use, or ``None`` to fall back to the mock."""
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
        "--verbose", "-v", action="store_true", help="Enable DEBUG-level logging."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    driver: AnalyzerDriver
    if args.mock:
        driver = MockDriver()
    else:
        resource = _pick_resource(args.resource)
        if resource is None:
            return 1
        driver = FlexDriver(resource)

    try:
        with driver:
            print(f"*IDN? -> {driver.idn()}")
    except CommunicationError as exc:
        print(f"Communication error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
