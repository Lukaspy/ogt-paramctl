"""Result models — minimal shell for now; populated when the engine lands.

The engine streams samples via callbacks during a measurement, then assembles
a ``MeasurementResult`` at the end. The samples themselves are flat enough
to live in numpy arrays; the model wraps them with metadata for export.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .channel import ChannelId
from .setup import Setup


class Sample(BaseModel):
    """A single row of a measurement result.

    Attributes:
        index: Zero-based sample index within the run.
        var1_value: Value of VAR1 at this sample (sweep only; ``None`` for
            sampling and spot modes).
        var2_value: Value of VAR2 at this sample (only on outer-loop steps
            in a sweep with VAR2; ``None`` otherwise).
        readings: Channel-keyed map of measured values. Units are amps for
            current measurements, volts for voltage measurements; the
            channel's mode determines which.
        timestamp: Seconds since the start of the run; ``None`` if the
            instrument did not provide a timestamp.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int = Field(ge=0)
    var1_value: float | None = None
    var2_value: float | None = None
    readings: dict[ChannelId, float] = Field(default_factory=dict)
    timestamp: float | None = None


class MeasurementResult(BaseModel):
    """Finalised result of a single measurement run.

    Attributes:
        setup: The setup that produced this run; serialised verbatim so a
            CSV (or HDF5) export carries enough metadata to reproduce the
            measurement.
        samples: Captured rows in acquisition order.
        started_at: Epoch seconds when the run began.
        completed_at: Epoch seconds when the run ended (``None`` if aborted
            before any sample was taken).
        aborted: ``True`` if the user (or a safety condition) stopped the
            run before its natural end.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    setup: Setup
    samples: list[Sample]
    started_at: float
    completed_at: float | None = None
    aborted: bool = False


__all__ = ["MeasurementResult", "Sample"]
