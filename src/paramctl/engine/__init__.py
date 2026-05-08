"""Measurement orchestration layer.

The engine sits between a ``Setup`` (what to measure) and an
``AnalyzerDriver`` (the instrument). It is Qt-free and synchronous; the
ui layer wraps it in a worker thread.
"""
from __future__ import annotations

from .events import (
    SampleReady,
    SweepCompleted,
    SweepEvent,
    SweepFailed,
    SweepStarted,
)
from .runner import run_sweep

__all__ = [
    "SampleReady",
    "SweepCompleted",
    "SweepEvent",
    "SweepFailed",
    "SweepStarted",
    "run_sweep",
]
