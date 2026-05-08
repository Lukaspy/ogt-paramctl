"""Unit tests for the ``AnalyzerDriver`` ABC contract."""
from __future__ import annotations

from inspect import isabstract

import pytest

from paramctl.driver import AnalyzerDriver, MockDriver


def test_abc_cannot_be_instantiated() -> None:
    assert isabstract(AnalyzerDriver)
    with pytest.raises(TypeError):
        AnalyzerDriver()  # type: ignore[abstract]


def test_concrete_driver_satisfies_abc() -> None:
    drv = MockDriver()
    assert isinstance(drv, AnalyzerDriver)


def test_partial_implementation_is_still_abstract() -> None:
    """A subclass missing any abstract method must remain non-instantiable."""

    class HalfBaked(AnalyzerDriver):
        def connect(self) -> None: ...
        def disconnect(self) -> None: ...
        def idn(self) -> str:
            return ""
        # missing: reset, is_connected

    assert isabstract(HalfBaked)
    with pytest.raises(TypeError):
        HalfBaked()  # type: ignore[abstract]
