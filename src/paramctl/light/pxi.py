"""Production light source: the 8-channel NI PXI-7853R LED driver.

``PxiLightSource`` adapts ``led_driver.LEDController`` (from the PXI-AWG
repo) to the :class:`LightSource` interface. This is the same physical
source the MFIA C-f/C-t tools drive; the user refers to it colloquially as
"the Mightex" (the PXI-7853R FPGA generates the 0-10 V analog modulation
that drives a Mightex unit with dumb analog inputs).

The ``led_driver`` import is deferred to :meth:`connect`, so this package
never hard-depends on it: the mock path and the test suite run without it
installed. With ``bitfile=None`` the driver runs its own mock backend (no
FPGA / no ``nifpga`` needed), which is handy for exercising this adapter
end-to-end against the real controller class.
"""
from __future__ import annotations

from typing import Any

from .base import (
    LightSource,
    LightSourceError,
    NotConnectedError,
    UnknownWavelengthError,
)
from .mock import DEFAULT_WAVELENGTHS_NM


class PxiLightSource(LightSource):
    """Adapter over ``led_driver.LEDController`` (NI PXI-7853R).

    Args:
        bitfile: Compiled ``.lvbitx`` FPGA bitfile. ``None`` runs the
            ``led_driver`` package's own mock backend -- exercises this
            adapter without hardware.
        resource: NI-RIO resource name (default ``"RIO0"``).
        use_cal: Apply the ``led_driver`` power calibration so equal ``pct``
            across wavelengths yields equal optical power. Uncalibrated
            channels pass through linearly.
    """

    def __init__(
        self,
        bitfile: str | None = None,
        resource: str = "RIO0",
        use_cal: bool = False,
    ) -> None:
        self.bitfile = bitfile
        self.resource = resource
        self.use_cal = use_cal
        self._ctl: Any = None
        # Effective full-scale current per wavelength (full_scale x current_scale),
        # cached on connect for current_ma_for.
        self._effective_fs_ma: dict[float, float] = {}

    def connect(self) -> None:
        try:
            from led_driver import LEDController
        except ImportError as exc:
            raise LightSourceError(
                "led_driver is not importable. Clone the PXI-AWG repo and put "
                "its directory on PYTHONPATH (or drop a .pth pointing at it into "
                "this venv's site-packages). Original error: " + str(exc)
            ) from exc

        ctl = LEDController(
            self.bitfile,
            self.resource,
            use_cal=self.use_cal,
            auto_connect=False,
        )
        if not ctl.connect():
            raise LightSourceError(
                f"LEDController.connect() failed for resource {self.resource!r} "
                f"(bitfile={self.bitfile!r})."
            )
        self._ctl = ctl
        # Cache effective full-scale (full_scale x current_scale) so the
        # reported current reflects the per-channel safety limit, not the raw
        # driver full-scale.
        self._effective_fs_ma = {}
        for ch in ctl.channels():
            wl = ch.get("wavelength_nm")
            if wl is not None:
                fs = float(ch.get("full_scale_ma", 0.0))
                scale = float(ch.get("current_scale", 1.0))
                self._effective_fs_ma[float(wl)] = fs * scale

    def disconnect(self) -> None:
        if self._ctl is not None:
            try:
                self._ctl.disconnect()
            finally:
                self._ctl = None

    def idn(self) -> str:
        mode = "mock" if self.bitfile is None else f"FPGA {self.resource}"
        return f"PXI-7853R 8-ch LED driver ({mode})"

    @property
    def is_connected(self) -> bool:
        return self._ctl is not None

    def wavelengths(self) -> list[float]:
        if self._ctl is None:
            return list(DEFAULT_WAVELENGTHS_NM)
        return [float(w) for w in self._ctl.wavelengths()]

    def channel_of(self, nm: float) -> int:
        if self._ctl is None:
            raise NotConnectedError("channel_of() before connect()")
        try:
            return int(self._ctl.channel_of(nm))
        except (KeyError, ValueError) as exc:
            raise UnknownWavelengthError(f"No channel at {nm} nm.") from exc

    def set_intensity(self, nm: float, pct: float) -> None:
        if self._ctl is None:
            raise NotConnectedError("set_intensity() before connect()")
        self._ctl.set_intensity(nm=nm, pct=pct)

    def all_off(self) -> None:
        if self._ctl is not None:
            self._ctl.all_off()

    def current_ma_for(self, nm: float, pct: float) -> float | None:
        fs = self._effective_fs_ma.get(float(nm))
        if fs is None:
            return None
        return (pct / 100.0) * fs

    def predicted_power_mw(self, nm: float, pct: float) -> float | None:
        if self._ctl is None:
            return None
        try:
            ch = self._ctl.channel_of(nm)
            cal = self._ctl.cal.channels[ch]
            if not cal.is_calibrated:
                return None
            if self._ctl.use_cal and self._ctl.cal.equalize:
                eq = self._ctl.cal.equalized_max_power
                if eq != float("inf"):
                    return float((pct / 100.0) * eq)
                return float(cal.drive_to_power(pct))
            if self._ctl.use_cal:
                return (pct / 100.0) * float(cal.max_power)
            return float(cal.drive_to_power(pct))
        except Exception:
            return None


__all__ = ["PxiLightSource"]
