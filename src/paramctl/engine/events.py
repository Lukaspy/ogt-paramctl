"""Events emitted by the engine while running a measurement.

Events are plain frozen dataclasses, not Pydantic models — they cross thread
boundaries inside the QThread worker (in the ui layer) and need to stay
trivially picklable and cheap to construct. The discriminated nature is
expressed through the ``SweepEvent`` union; the ui layer dispatches on
``isinstance``.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models.results import Sample
from ..models.setup import Setup


@dataclass(frozen=True, slots=True)
class SweepStarted:
    """Emitted exactly once at the beginning of a run."""

    setup: Setup


@dataclass(frozen=True, slots=True)
class SampleReady:
    """Emitted once per sample produced by the driver."""

    sample: Sample


@dataclass(frozen=True, slots=True)
class SweepCompleted:
    """Emitted exactly once at the end of a successful or aborted run.

    Attributes:
        aborted: ``True`` when the engine cancelled the run via the abort
            event; ``False`` when the driver completed naturally.
        sample_count: How many samples were yielded before the run ended.
    """

    aborted: bool
    sample_count: int


@dataclass(frozen=True, slots=True)
class SweepFailed:
    """Emitted exactly once when the driver raised an exception mid-run.

    The exception is preserved so the ui can show the user a meaningful
    error; the engine does not re-raise.
    """

    exception: BaseException
    sample_count: int


SweepEvent = SweepStarted | SampleReady | SweepCompleted | SweepFailed
"""Tagged union of every event the engine can emit."""


__all__ = [
    "SampleReady",
    "SweepCompleted",
    "SweepEvent",
    "SweepFailed",
    "SweepStarted",
]
