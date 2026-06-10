"""Measurement orchestration layer.

The engine sits between a ``Setup`` (what to measure) and an
``AnalyzerDriver`` (the instrument). It is Qt-free and synchronous; the
ui layer wraps it in a worker thread. ``run_campaign`` adds a second
orchestration on top: many sweeps under varied illumination.
"""
from __future__ import annotations

from .campaign import run_campaign
from .events import (
    CampaignCompleted,
    CampaignEvent,
    CampaignFailed,
    CampaignStarted,
    SampleReady,
    StepCompleted,
    StepSample,
    StepStarted,
    SweepCompleted,
    SweepEvent,
    SweepFailed,
    SweepStarted,
)
from .runner import run_sweep

__all__ = [
    "CampaignCompleted",
    "CampaignEvent",
    "CampaignFailed",
    "CampaignStarted",
    "SampleReady",
    "StepCompleted",
    "StepSample",
    "StepStarted",
    "SweepCompleted",
    "SweepEvent",
    "SweepFailed",
    "SweepStarted",
    "run_campaign",
    "run_sweep",
]
