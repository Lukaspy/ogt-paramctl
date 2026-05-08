"""Pydantic models — the lingua franca between every layer.

Models describe *what* a measurement is, not *how* a specific instrument
runs it. Driver-specific quirks live in the driver layer; if a field only
makes sense for the 4155/4156, it does not belong here.
"""
from __future__ import annotations

from .channel import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelLimits,
    ChannelMode,
    is_smu,
    is_vmu,
    is_vsu,
)
from .measurement import (
    IntegrationTime,
    MeasurementMode,
    SamplingMeasurement,
    SpotMeasurement,
    SweepDirection,
    SweepMeasurement,
    SweepRange,
    SweepScale,
    Var1PrimeLink,
)
from .results import MeasurementResult, Sample
from .setup import CURRENT_SCHEMA_VERSION, Setup

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "ChannelConfig",
    "ChannelFunction",
    "ChannelId",
    "ChannelLimits",
    "ChannelMode",
    "IntegrationTime",
    "MeasurementMode",
    "MeasurementResult",
    "Sample",
    "SamplingMeasurement",
    "SpotMeasurement",
    "Setup",
    "SweepDirection",
    "SweepMeasurement",
    "SweepRange",
    "SweepScale",
    "Var1PrimeLink",
    "is_smu",
    "is_vmu",
    "is_vsu",
]
