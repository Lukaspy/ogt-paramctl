"""Synthetic driver that satisfies ``AnalyzerDriver`` without any I/O.

``MockDriver`` is the backbone of mock-first development. The whole stack —
engine, persistence, ui — must work end-to-end against this driver so that
contributors do not need a real 4155/4156 on the bench to make progress.

In the current step the mock only supports identification and reset. As
later milestones add measurement methods to ``AnalyzerDriver``, the mock
grows physically plausible synthetic data (BSIM-ish MOSFETs, Shockley
diodes, linear resistors) so that plots look right.
"""
from __future__ import annotations

import logging

from .base import AnalyzerDriver, NotConnectedError

logger = logging.getLogger(__name__)


class MockDriver(AnalyzerDriver):
    """In-memory ``AnalyzerDriver`` returning a fixed IDN and tracking state.

    The default IDN identifies the model as ``4155B`` (so model-detection
    code works) but encodes ``MOCK`` in the serial and firmware fields so
    that anyone reading a log can tell at a glance the data did not come
    from real hardware.

    Attributes:
        DEFAULT_IDN: Default IDN response when no override is supplied.
    """

    DEFAULT_IDN: str = "Agilent Technologies,4155B,MOCK-0000000,REV99.99-MOCK"

    def __init__(self, idn: str = DEFAULT_IDN) -> None:
        """Construct a mock driver.

        Args:
            idn: IDN string to return from ``idn()``. Defaults to a 4155B
                identifier with ``MOCK`` markers in the serial/firmware fields.
        """
        self._idn = idn
        self._connected = False
        self._reset_count = 0

    def connect(self) -> None:
        logger.debug("MockDriver.connect()")
        self._connected = True

    def disconnect(self) -> None:
        if self._connected:
            logger.debug("MockDriver.disconnect()")
        self._connected = False

    def idn(self) -> str:
        if not self._connected:
            raise NotConnectedError("MockDriver is not connected")
        return self._idn

    def reset(self) -> None:
        if not self._connected:
            raise NotConnectedError("MockDriver is not connected")
        self._reset_count += 1
        logger.debug("MockDriver.reset() (count=%d)", self._reset_count)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def reset_count(self) -> int:
        """Number of times ``reset()`` has been called.

        Exposed for testability — callers can verify orchestration code
        actually issues a reset at the expected times.
        """
        return self._reset_count
