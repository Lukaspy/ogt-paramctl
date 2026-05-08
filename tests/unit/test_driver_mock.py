"""Unit tests for ``MockDriver``."""
from __future__ import annotations

import pytest

from paramctl.driver import MockDriver, NotConnectedError


def test_mock_starts_disconnected() -> None:
    drv = MockDriver()
    assert drv.is_connected is False


def test_mock_connect_sets_connected() -> None:
    drv = MockDriver()
    drv.connect()
    assert drv.is_connected is True


def test_mock_disconnect_clears_connected() -> None:
    drv = MockDriver()
    drv.connect()
    drv.disconnect()
    assert drv.is_connected is False


def test_disconnect_is_idempotent() -> None:
    drv = MockDriver()
    drv.disconnect()
    drv.connect()
    drv.disconnect()
    drv.disconnect()
    assert drv.is_connected is False


def test_default_idn_is_4155b_with_mock_marker() -> None:
    drv = MockDriver()
    drv.connect()
    idn = drv.idn()
    fields = [f.strip() for f in idn.split(",")]
    assert len(fields) == 4
    vendor, model, serial, firmware = fields
    assert model == "4155B", f"model field should be exactly '4155B', got {model!r}"
    assert "MOCK" in serial or "MOCK" in firmware, (
        f"serial or firmware must mark this a mock; "
        f"got serial={serial!r} firmware={firmware!r}"
    )
    assert vendor  # non-empty


def test_idn_before_connect_raises() -> None:
    drv = MockDriver()
    with pytest.raises(NotConnectedError):
        drv.idn()


def test_reset_before_connect_raises() -> None:
    drv = MockDriver()
    with pytest.raises(NotConnectedError):
        drv.reset()


def test_reset_increments_count() -> None:
    drv = MockDriver()
    drv.connect()
    assert drv.reset_count == 0
    drv.reset()
    drv.reset()
    assert drv.reset_count == 2


def test_custom_idn_is_returned_verbatim() -> None:
    custom = "FakeCorp,FakeModel,SN-1,FW1.0"
    drv = MockDriver(idn=custom)
    drv.connect()
    assert drv.idn() == custom


def test_context_manager_lifecycle() -> None:
    drv = MockDriver()
    with drv as ctx_drv:
        assert ctx_drv is drv
        assert drv.is_connected is True
        assert "4155B" in drv.idn()
    assert drv.is_connected is False


def test_idn_after_disconnect_raises() -> None:
    drv = MockDriver()
    drv.connect()
    drv.idn()
    drv.disconnect()
    with pytest.raises(NotConnectedError):
        drv.idn()
