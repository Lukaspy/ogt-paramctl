"""The :class:`PhotoIvCampaign` model: a staged photo-IV measurement run.

A campaign pairs one base IV :class:`Setup` (the sweep template -- channels,
bias range, compliance) with an :class:`IlluminationSequence` (the light
plan). The engine takes the base setup and re-runs it once per illumination
step, applying the step's light state and dwelling its settle time first, with
an optional fixed delay between consecutive measurements.

Driver-agnostic, like every other model: it says *what* to measure under
*what* light, not how a particular analyzer or LED source carries it out.
"""
from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .illumination import IlluminationSequence
from .measurement import SweepMeasurement, SweepRange
from .setup import Setup


def _range_label(r: SweepRange) -> str:
    """Compact filename-friendly tag for a sweep range, e.g. ``0to+7V``."""
    return f"{r.start:g}to{r.stop:+g}V"


class PhotoIvCampaign(BaseModel):
    """A full photo-IV campaign specification.

    Attributes:
        base_setup: The IV sweep template re-run at each illumination step.
            Its measurement must be a :class:`SweepMeasurement` (an IV curve).
        illumination: The ordered light plan; the IV measurement is repeated
            per step.
        sweep_ranges: Optional list of VAR1 ranges run back-to-back as a single
            measurement at each step. ``None`` (the default) runs one sweep per
            step using ``base_setup``'s own VAR1 range. Set to two ranges --
            e.g. 0->+7 V and 0->-7 V -- to take a dual-polarity pair at every
            step. The ranges override only VAR1; channels, compliance, and
            integration come from ``base_setup``.
        inter_step_delay_s: Default wait inserted *after* a step's sweep(s),
            before the next step. A step's own ``post_delay_s`` overrides this
            when set. In addition to each step's ``settle_s`` dwell.
        device_id: Device identifier, recorded in every output file.
        substrate_type: Substrate / material tag, recorded in every file.
        notes: Free-form notes carried into the metadata.
        output_dir: Destination folder for the per-curve CSV files. Empty
            means the caller chooses at run time.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_setup: Setup
    illumination: IlluminationSequence
    sweep_ranges: list[SweepRange] | None = None
    inter_step_delay_s: float = Field(default=0.0, ge=0.0)
    device_id: str = ""
    substrate_type: str = ""
    notes: str = ""
    output_dir: str = ""

    @model_validator(mode="after")
    def _validate_base_is_sweep(self) -> Self:
        if not isinstance(self.base_setup.measurement, SweepMeasurement):
            raise ValueError(
                "PhotoIvCampaign.base_setup must be an IV sweep "
                f"(SweepMeasurement); got {type(self.base_setup.measurement).__name__}."
            )
        if self.sweep_ranges is not None and not self.sweep_ranges:
            raise ValueError("sweep_ranges, when set, must contain at least one range.")
        return self

    def setups_for_step(self) -> list[tuple[str, Setup]]:
        """The ``(curve_label, setup)`` pairs to run at each illumination step.

        With no ``sweep_ranges`` this is a single ``("", base_setup)`` pair, so
        the per-curve label stays empty and filenames are unchanged. With
        ``sweep_ranges`` set it is one pair per range, each a copy of
        ``base_setup`` with VAR1 replaced and a label like ``0to+7V``.
        """
        if not self.sweep_ranges:
            return [("", self.base_setup)]
        base = self.base_setup
        pairs: list[tuple[str, Setup]] = []
        for r in self.sweep_ranges:
            measurement = base.measurement.model_copy(update={"var1": r})
            setup = base.model_copy(update={"measurement": measurement})
            pairs.append((_range_label(r), setup))
        return pairs


__all__ = ["PhotoIvCampaign"]
