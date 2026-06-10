"""In-memory fake light source for mock-first development and tests.

``MockLightSource`` implements the full :class:`LightSource` interface with
no hardware and no ``led_driver`` dependency, so the whole photo-IV campaign
-- including the GUI -- runs end-to-end on a laptop. It records the call
sequence and tracks which single channel is currently lit, which makes it
easy to assert the dark-pre / lit / dark-post ordering in tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .base import LightSource, NotConnectedError, UnknownWavelengthError

# Canonical physical wiring of the 8-channel LED source (Ch0=850 nm ... Ch7=385
# nm), matching led_driver.config.DEFAULT_WAVELENGTHS_NM and the MFIA tools.
DEFAULT_WAVELENGTHS_NM: list[float] = [850.0, 740.0, 625.0, 590.0, 530.0, 505.0, 470.0, 385.0]


@dataclass
class _Call:
    """One recorded interaction with the mock, for test assertions."""

    name: str
    kwargs: dict[str, float] = field(default_factory=dict)


class MockLightSource(LightSource):
    """Synthetic light source: records calls, tracks the lit channel.

    Args:
        wavelengths: Addressable channels (nm). Defaults to the canonical
            8-channel wiring.
        power_model_mw: Optional ``{wavelength: max_power_mw}`` used by
            :meth:`predicted_power_mw` (scaled linearly by drive %). ``None``
            leaves every channel uncalibrated, matching a real source with no
            calibration loaded.
    """

    def __init__(
        self,
        wavelengths: list[float] | None = None,
        power_model_mw: dict[float, float] | None = None,
    ) -> None:
        self._wavelengths = list(wavelengths or DEFAULT_WAVELENGTHS_NM)
        self.calls: list[_Call] = []
        # {nm: pct} of the single channel last set; cleared by dark/all_off.
        self.active: dict[float, float] = {}
        self._connected = False
        self._power_model_mw = power_model_mw
        # Mirror the led_driver defaults: 1000 mA full-scale everywhere except
        # 590 nm, software current-limited to 700 mA.
        self._effective_fs_ma = {
            wl: (700.0 if wl == 590.0 else 1000.0) for wl in self._wavelengths
        }

    def connect(self) -> None:
        self.calls.append(_Call("connect"))
        self._connected = True

    def disconnect(self) -> None:
        self.calls.append(_Call("disconnect"))
        self._connected = False

    def idn(self) -> str:
        return "MOCK,PXI-LED,0,0"

    @property
    def is_connected(self) -> bool:
        return self._connected

    def wavelengths(self) -> list[float]:
        return list(self._wavelengths)

    def channel_of(self, nm: float) -> int:
        try:
            return self._wavelengths.index(float(nm))
        except ValueError as exc:
            raise UnknownWavelengthError(
                f"No channel at {nm} nm. Available: {self._wavelengths}"
            ) from exc

    def set_intensity(self, nm: float, pct: float) -> None:
        if not self._connected:
            raise NotConnectedError("set_intensity() before connect()")
        if float(nm) not in self._wavelengths:
            raise UnknownWavelengthError(
                f"No channel at {nm} nm. Available: {self._wavelengths}"
            )
        self.calls.append(_Call("set_intensity", {"nm": float(nm), "pct": float(pct)}))
        self.active = {float(nm): float(pct)}

    def all_off(self) -> None:
        self.calls.append(_Call("all_off"))
        self.active = {}

    def current_ma_for(self, nm: float, pct: float) -> float | None:
        fs = self._effective_fs_ma.get(float(nm))
        if fs is None:
            return None
        return (pct / 100.0) * fs

    def predicted_power_mw(self, nm: float, pct: float) -> float | None:
        if self._power_model_mw is None:
            return None
        max_mw = self._power_model_mw.get(float(nm))
        if max_mw is None:
            return None
        return (pct / 100.0) * max_mw


__all__ = ["DEFAULT_WAVELENGTHS_NM", "MockLightSource"]
