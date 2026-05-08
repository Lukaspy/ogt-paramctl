"""Abstract base class and exception hierarchy for instrument drivers.

The ``AnalyzerDriver`` class is the seam where new instrument support is
added. Concrete drivers (``FlexDriver`` for the 4155/4156, ``MockDriver``
for synthetic data, future B1500A and 4145B drivers) implement this
interface; layers above the driver — engine, persistence, ui — must work
against the abstract type only.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self


class DriverError(Exception):
    """Base class for all driver-layer errors."""


class NotConnectedError(DriverError):
    """Raised when an operation is attempted on a disconnected driver."""


class CommunicationError(DriverError):
    """Raised when the underlying transport (VISA / USBTMC) reports a failure."""


class AnalyzerDriver(ABC):
    """Abstract interface every Semiconductor Parameter Analyzer driver implements.

    Drivers are synchronous. Threading concerns belong to the engine and ui
    layers — the driver itself must remain Qt-free and event-loop-free, so
    higher layers can wrap it in a ``QThread`` worker without contortion.

    Lifecycle:
        1. Construct with transport-specific arguments (e.g. a VISA resource
           string for ``FlexDriver``; nothing for ``MockDriver``).
        2. Call ``connect()`` to open the transport.
        3. Use ``idn()``, ``reset()``, and (eventually) measurement methods.
        4. Call ``disconnect()`` to release the transport.

    The ABC is also a context manager, so callers may write::

        with FlexDriver("GPIB0::17::INSTR") as drv:
            print(drv.idn())
    """

    @abstractmethod
    def connect(self) -> None:
        """Open the transport and put the instrument into a known state.

        Raises:
            CommunicationError: If the transport cannot be opened or the
                instrument fails to respond.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Close the transport. Idempotent; calling on a closed driver is a no-op."""

    @abstractmethod
    def idn(self) -> str:
        """Query the instrument's IEEE 488.2 ``*IDN?`` identification string.

        Returns:
            The raw IDN response, comma-separated as
            ``vendor,model,serial,firmware``.

        Raises:
            NotConnectedError: If called before ``connect()``.
            CommunicationError: If the underlying transport reports a failure.
        """

    @abstractmethod
    def reset(self) -> None:
        """Send ``*RST`` to return the instrument to its power-on default state.

        Raises:
            NotConnectedError: If called before ``connect()``.
            CommunicationError: If the underlying transport reports a failure.
        """

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True if ``connect()`` has been called and ``disconnect()`` has not."""

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.disconnect()
