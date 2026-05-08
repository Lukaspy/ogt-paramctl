"""Measurement-mode models: sweep, sampling, spot — and their shared types.

The 4155/4156 supports three top-level measurement modes. v1 implements
sweep end-to-end; sampling and spot are present as shells so future work
slots in cleanly without reshaping the discriminated union.
"""
from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IntegrationTime(str, Enum):
    """Measurement integration time setting (4155/4156 ``IT`` levels).

    Maps to the FLEX ``IT`` command. ``MEDIUM`` is the typical default.
    """

    SHORT = "SHORT"
    MEDIUM = "MEDIUM"
    LONG = "LONG"


class SweepScale(str, Enum):
    """Spacing of sweep points between start and stop."""

    LINEAR = "LINEAR"
    LOG10 = "LOG10"
    LOG25 = "LOG25"
    LOG50 = "LOG50"


class SweepDirection(str, Enum):
    """Sweep traversal pattern."""

    SINGLE = "SINGLE"  # start -> stop
    DOUBLE = "DOUBLE"  # start -> stop -> start


class SweepRange(BaseModel):
    """Numeric range specification for a single sweep variable.

    Attributes:
        start: First value sourced (volts or amps depending on the channel).
        stop: Final value sourced.
        points: Number of points; must be at least 2.
        scale: Linear or one of the FLEX log-decade variants.
        direction: Single (start -> stop) or double (start -> stop -> start).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    start: float
    stop: float
    points: int = Field(ge=2)
    scale: SweepScale = SweepScale.LINEAR
    direction: SweepDirection = SweepDirection.SINGLE

    @model_validator(mode="after")
    def _validate_range(self) -> Self:
        if self.start == self.stop:
            raise ValueError("sweep start and stop must differ.")

        if self.scale is not SweepScale.LINEAR and self.start * self.stop <= 0:
            raise ValueError(
                "log sweep cannot cross or touch zero; "
                "start and stop must have the same non-zero sign."
            )

        return self


class Var1PrimeLink(BaseModel):
    """Linkage of VAR1' to VAR1: ``VAR1' = VAR1 * ratio + offset``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ratio: float = 1.0
    offset: float = 0.0


class SweepMeasurement(BaseModel):
    """DC sweep measurement: VAR1 (and optionally VAR2 / VAR1') swept across a range.

    Attributes:
        kind: Discriminator literal ``"sweep"``.
        var1: Required primary sweep range.
        var2: Optional secondary sweep — produces a family of curves
            (e.g. Id-Vds at multiple Vgs).
        var1_prime: Optional VAR1' link — second channel slaved to VAR1.
        hold_time: Seconds to hold the initial state before the first
            measurement (lets bias-dependent transients settle).
        delay_time: Seconds to wait between setting a sweep value and
            taking the measurement.
        integration: Integration time level passed to the instrument.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["sweep"] = "sweep"
    var1: SweepRange
    var2: SweepRange | None = None
    var1_prime: Var1PrimeLink | None = None
    hold_time: float = Field(default=0.0, ge=0)
    delay_time: float = Field(default=0.0, ge=0)
    integration: IntegrationTime = IntegrationTime.MEDIUM


class SamplingMeasurement(BaseModel):
    """Time-domain sampling measurement (transient capture).

    v1 ships only the model shell; the engine support lands in a later
    milestone.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["sampling"] = "sampling"
    interval: float = Field(gt=0)
    points: int = Field(ge=2)
    hold_time: float = Field(default=0.0, ge=0)
    integration: IntegrationTime = IntegrationTime.SHORT


class SpotMeasurement(BaseModel):
    """Single-point DC measurement at the channels' configured CONST values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["spot"] = "spot"
    integration: IntegrationTime = IntegrationTime.MEDIUM


MeasurementMode = Annotated[
    SweepMeasurement | SamplingMeasurement | SpotMeasurement,
    Field(discriminator="kind"),
]
"""Discriminated union of supported measurement modes.

Pydantic dispatches on the ``kind`` literal at parse time, which makes YAML
round-tripping trivial: persisted setups carry ``kind: sweep`` (etc.) and
load back into the right concrete type.
"""


__all__ = [
    "IntegrationTime",
    "MeasurementMode",
    "SamplingMeasurement",
    "SpotMeasurement",
    "SweepDirection",
    "SweepMeasurement",
    "SweepRange",
    "SweepScale",
    "Var1PrimeLink",
]
