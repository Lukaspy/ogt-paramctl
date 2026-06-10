"""Events emitted by the engine while running a measurement.

Events are plain frozen dataclasses, not Pydantic models — they cross thread
boundaries inside the QThread worker (in the ui layer) and need to stay
trivially picklable and cheap to construct. The discriminated nature is
expressed through the ``SweepEvent`` union; the ui layer dispatches on
``isinstance``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models.campaign import PhotoIvCampaign
from ..models.illumination import IlluminationStep
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
"""Tagged union of every event a single sweep can emit."""


# --- Photo-IV campaign events ------------------------------------------------
# A campaign runs many sweeps under different illumination. These events wrap
# the per-step lifecycle so the ui can show queue progress and tag each live
# IV trace with the step that produced it.


@dataclass(frozen=True, slots=True)
class CampaignStarted:
    """Emitted exactly once when a campaign begins.

    Attributes:
        campaign: The full campaign specification being run.
        total_steps: Number of illumination steps (== IV curves) queued.
    """

    campaign: PhotoIvCampaign
    total_steps: int


@dataclass(frozen=True, slots=True)
class StepStarted:
    """Emitted when a step's light state is applied, before its sweep runs.

    Attributes:
        step_index: Zero-based index of this step in the sequence.
        step: The illumination step (wavelength / intensity / dark).
    """

    step_index: int
    step: IlluminationStep


@dataclass(frozen=True, slots=True)
class StepSample:
    """Emitted once per sample of a step's IV sweep, tagged with the step.

    Attributes:
        step_index: Which step this sample belongs to.
        sample: The sweep sample.
        curve_index: Which sweep within the step (0 unless the step runs more
            than one range, e.g. a dual-polarity pair).
        curve_label: Tag for the curve's range (``""`` for the single-curve
            default; e.g. ``"0to+7V"`` for a multi-range step).
    """

    step_index: int
    sample: Sample
    curve_index: int = 0
    curve_label: str = ""


@dataclass(frozen=True, slots=True)
class StepCompleted:
    """Emitted at the end of each sweep of a step (natural or aborted).

    One event per curve: a step with two sweep ranges emits two. The collected
    samples travel with the event so the caller (the Qt worker) can write the
    per-curve CSV; the engine itself never touches disk, keeping it
    mock-testable.

    Attributes:
        step_index: Which step this curve belongs to.
        step: The illumination step that produced the curve.
        samples: All samples captured for this curve, in order.
        aborted: ``True`` if the sweep was cancelled before its natural end.
        curve_index: Which sweep within the step (0 for the single-curve case).
        curve_label: Tag for the curve's range (``""`` for the single-curve
            default).
    """

    step_index: int
    step: IlluminationStep
    samples: list[Sample] = field(default_factory=list)
    aborted: bool = False
    curve_index: int = 0
    curve_label: str = ""


@dataclass(frozen=True, slots=True)
class CampaignCompleted:
    """Emitted exactly once at the end of a campaign (natural or aborted).

    Attributes:
        aborted: ``True`` if the campaign was cancelled before finishing.
        steps_completed: How many steps produced a (possibly partial) sweep.
    """

    aborted: bool
    steps_completed: int


@dataclass(frozen=True, slots=True)
class CampaignFailed:
    """Emitted once if a step's sweep raised; the campaign stops.

    Attributes:
        exception: The captured exception (not re-raised by the engine).
        step_index: The step during which the failure occurred.
    """

    exception: BaseException
    step_index: int


CampaignEvent = (
    CampaignStarted
    | StepStarted
    | StepSample
    | StepCompleted
    | CampaignCompleted
    | CampaignFailed
)
"""Tagged union of every event a campaign run can emit."""


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
]
