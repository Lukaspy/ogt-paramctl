"""Instrument driver layer.

The driver layer is the only place in ``paramctl`` that talks to the
instrument. The abstract ``AnalyzerDriver`` defines the contract; concrete
drivers (``FlexDriver`` for the 4155/4156 family, ``MockDriver`` for
synthetic data, future B1500A and 4145B drivers) implement it.

Layers above this one — engine, persistence, ui — must depend on the
abstract type, not on a concrete driver.
"""
from __future__ import annotations

from .base import (
    AnalyzerDriver,
    CommunicationError,
    DriverError,
    NotConnectedError,
)
from .discovery import list_resources
from .flex import FlexDriver
from .mock import MockDriver

__all__ = [
    "AnalyzerDriver",
    "CommunicationError",
    "DriverError",
    "FlexDriver",
    "MockDriver",
    "NotConnectedError",
    "list_resources",
]
