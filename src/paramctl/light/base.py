"""Abstract base class and errors for the optical (LED) source.

The photo-IV campaign drives a multi-wavelength LED source alongside the
parameter analyzer. Like ``AnalyzerDriver``, the ``LightSource`` ABC is the
seam where a concrete source implementation plugs in; layers above it
(engine, ui) work against the abstract type only and stay hardware-agnostic.

The source is addressed **by wavelength (nm)** and driven by **intensity
percent (0-100 %)** -- not by current. The concrete driver maps percent to
drive current internally (per-channel full-scale + safety limits). This
mirrors the established convention of the MFIA C-f/C-t tools, which drive the
same physical 8-channel NI PXI-7853R LED source.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self


class LightSourceError(Exception):
    """Base class for all light-source errors."""


class NotConnectedError(LightSourceError):
    """Raised when an operation is attempted on a disconnected source."""


class UnknownWavelengthError(LightSourceError):
    """Raised when a wavelength has no channel on this source."""


class LightSource(ABC):
    """Abstract interface for a multi-wavelength LED source.

    Sources are synchronous and Qt-free; threading concerns belong to the
    engine and ui layers, exactly as for :class:`~paramctl.driver.base.AnalyzerDriver`.

    Lifecycle mirrors the analyzer driver:

        1. Construct with transport-specific arguments.
        2. ``connect()`` to open the transport.
        3. ``set_intensity()`` / ``all_off()`` to drive channels.
        4. ``disconnect()`` to release the transport.

    The ABC is a context manager, so callers may write::

        with PxiLightSource() as led:
            led.set_intensity(385.0, 50.0)
    """

    @abstractmethod
    def connect(self) -> None:
        """Open the transport and put the source in a known (all-off) state.

        Raises:
            LightSourceError: If the transport cannot be opened.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Close the transport. Idempotent; a no-op on an already-closed source."""

    @abstractmethod
    def idn(self) -> str:
        """Return a human-readable identification string for the source."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True if ``connect()`` has been called and ``disconnect()`` has not."""

    @abstractmethod
    def wavelengths(self) -> list[float]:
        """Wavelengths (nm) of every addressable channel, in channel order."""

    @abstractmethod
    def channel_of(self, nm: float) -> int:
        """Return the 0-based channel index wired to ``nm``.

        Raises:
            UnknownWavelengthError: If no channel is wired to ``nm``.
        """

    @abstractmethod
    def set_intensity(self, nm: float, pct: float) -> None:
        """Drive the channel at ``nm`` to ``pct`` (0-100 %) and enable it.

        Args:
            nm: Target wavelength; must match an addressable channel.
            pct: Commanded intensity in percent of the channel full-scale.

        Raises:
            NotConnectedError: If called before ``connect()``.
            UnknownWavelengthError: If no channel is wired to ``nm``.
        """

    @abstractmethod
    def all_off(self) -> None:
        """Zero and disable every channel. Safe to call when disconnected."""

    def current_ma_for(self, nm: float, pct: float) -> float | None:
        """Best-effort actual drive current (mA) for a wavelength + percent.

        Informational only -- folded into the per-curve metadata. Returns
        ``None`` if the channel's full-scale current is unknown. The default
        implementation returns ``None``; concrete sources may override.
        """
        return None

    def predicted_power_mw(self, nm: float, pct: float) -> float | None:
        """Calibration-predicted delivered optical power (mW), or ``None``.

        ``None`` for uncalibrated channels. The default implementation returns
        ``None``; concrete sources with a power calibration may override.
        """
        return None

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


__all__ = [
    "LightSource",
    "LightSourceError",
    "NotConnectedError",
    "UnknownWavelengthError",
]
