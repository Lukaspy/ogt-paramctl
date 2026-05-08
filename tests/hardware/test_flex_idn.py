"""Hardware smoke tests for ``FlexDriver`` against a real 4155/4156.

Run with::

    pytest -m hardware --resource='GPIB0::17::INSTR'

These tests are skipped by default because they require a physical
instrument plus a working VISA backend.
"""
from __future__ import annotations

import pytest

from paramctl.driver import FlexDriver

pytestmark = pytest.mark.hardware


def test_idn_identifies_4155_or_4156(visa_resource: str) -> None:
    """Connect, query ``*IDN?``, and assert the model field is in the family."""
    drv = FlexDriver(visa_resource)
    drv.connect()
    try:
        idn = drv.idn()
    finally:
        drv.disconnect()

    fields = [f.strip() for f in idn.split(",")]
    assert len(fields) >= 4, f"Malformed IDN response: {idn!r}"
    model = fields[1]
    assert any(family in model for family in ("4155", "4156")), (
        f"Connected instrument identifies as {model!r}; expected 4155/4156 family."
    )


def test_context_manager_closes_cleanly(visa_resource: str) -> None:
    """The context manager must connect on enter and disconnect on exit."""
    drv = FlexDriver(visa_resource)
    with drv:
        assert drv.is_connected is True
        drv.idn()
    assert drv.is_connected is False
