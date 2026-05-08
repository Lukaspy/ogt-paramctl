"""VISA resource discovery for the connection dialog and the test suite.

The connection dialog (added in a later step) calls ``list_resources()`` to
populate the resource picker. Resource strings are never hardcoded in
setups — they are chosen at connect time and stored alongside the setup if
the user wants the choice persisted.
"""
from __future__ import annotations

import logging

import pyvisa

logger = logging.getLogger(__name__)


def list_resources(query: str = "?*") -> list[str]:
    """Enumerate VISA resources visible to the active backend.

    Args:
        query: VISA resource-name pattern (``?*`` matches every resource).
            Restrict to a transport class with patterns like ``GPIB?*INSTR``
            or ``USB?*INSTR`` if needed.

    Returns:
        A list of resource strings (e.g. ``GPIB0::17::INSTR``,
        ``USB0::0x2A8D::0xFE03::MY12345678::INSTR``). Empty if no instruments
        are visible to the current backend.
    """
    rm = pyvisa.ResourceManager()
    try:
        resources = list(rm.list_resources(query))
    finally:
        rm.close()
    logger.debug("Discovered %d VISA resource(s) for query %r", len(resources), query)
    return resources
