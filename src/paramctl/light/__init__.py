"""Optical (LED) source layer for the photo-IV campaign.

Pure I/O, like ``driver/``: an abstract :class:`LightSource`, the
``led_driver``-backed :class:`PxiLightSource`, and a hardware-free
:class:`MockLightSource`. No Qt, no engine logic.
"""
from __future__ import annotations

from .base import (
    LightSource,
    LightSourceError,
    NotConnectedError,
    UnknownWavelengthError,
)
from .mock import DEFAULT_WAVELENGTHS_NM, MockLightSource
from .pxi import PxiLightSource

__all__ = [
    "DEFAULT_WAVELENGTHS_NM",
    "LightSource",
    "LightSourceError",
    "MockLightSource",
    "NotConnectedError",
    "PxiLightSource",
    "UnknownWavelengthError",
]
