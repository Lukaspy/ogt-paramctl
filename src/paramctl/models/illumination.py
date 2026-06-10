"""Illumination models for the photo-IV campaign.

An :class:`IlluminationSequence` is the ordered "plan" the campaign works
through: each :class:`IlluminationStep` sets one light state (a wavelength at
an intensity, or dark) and then one IV sweep is taken. Dark steps interleaved
between lit steps give the dark-pre / lit / dark-post pattern at every
measurement point -- the same convention as the MFIA C-f/C-t tools, so trap
/ persistent-photoconductivity recovery is captured between wavelengths.

These models are driver- and instrument-agnostic: they describe *what* light
state to apply, not *how* a specific LED source applies it.
"""
from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IlluminationStep(BaseModel):
    """One light state in the campaign sequence.

    The optical source is addressed by **wavelength** and driven by
    **intensity percent**. ``wavelength_nm`` of ``None`` means "all LEDs off"
    (dark); otherwise it selects the channel and ``intensity_pct`` (0-100) is
    the commanded drive.

    Attributes:
        label: Short tag used in the output filename and plot legend, e.g.
            ``"dark_pre"``, ``"385nm_50pct"``, ``"dark_post_385_50pct"``.
        wavelength_nm: Channel wavelength in nm; ``None`` for a dark step.
        intensity_pct: Commanded drive in percent of channel full-scale.
            Must be 0 for a dark step.
        settle_s: Seconds to dwell after applying this light state before the
            IV sweep(s) start (lets photo-transients settle).
        post_delay_s: Seconds to wait *after* this step's sweep(s) complete,
            before the next step. ``None`` falls back to the campaign-level
            ``inter_step_delay_s``. Builders use it to set different gaps at
            different points -- e.g. a short delay between intensity levels but
            a longer one after the last level, before the dark-post reference.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1)
    wavelength_nm: float | None = None
    intensity_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    settle_s: float = Field(default=0.0, ge=0.0)
    post_delay_s: float | None = Field(default=None, ge=0.0)

    @property
    def is_dark(self) -> bool:
        """True if this step leaves every LED off."""
        return self.wavelength_nm is None

    @model_validator(mode="after")
    def _validate_dark_intensity(self) -> Self:
        if self.wavelength_nm is None and self.intensity_pct != 0.0:
            raise ValueError("a dark step (wavelength_nm=None) must have intensity_pct=0.")
        return self


class IlluminationSequence(BaseModel):
    """Ordered list of :class:`IlluminationStep` -- the campaign's queue.

    One IV sweep is taken per step, in order. Builders below assemble the
    common patterns; the GUI also lets the user edit the list directly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    steps: list[IlluminationStep] = Field(min_length=1)

    def __len__(self) -> int:
        return len(self.steps)

    @classmethod
    def intensity_series(
        cls,
        wavelength_nm: float,
        drive_points_pct: list[float],
        *,
        dark_pre: bool = True,
        interleave_dark: bool = True,
        light_settle_s: float = 30.0,
        dark_settle_s: float = 60.0,
    ) -> Self:
        """A single wavelength stepped through several drive levels.

        The photo-response-vs-intensity sweep used to test whether the
        response is linear in flux. Dark is interleaved by default so
        persistent photoconductivity from one level recovers before the next.
        """
        steps: list[IlluminationStep] = []
        if dark_pre:
            steps.append(IlluminationStep(label="dark_pre", settle_s=dark_settle_s))
        for pct in drive_points_pct:
            steps.append(
                IlluminationStep(
                    label=f"{int(wavelength_nm)}nm_{pct:g}pct",
                    wavelength_nm=wavelength_nm,
                    intensity_pct=pct,
                    settle_s=light_settle_s,
                )
            )
            if interleave_dark:
                steps.append(
                    IlluminationStep(
                        label=f"dark_post_{int(wavelength_nm)}_{pct:g}pct",
                        settle_s=dark_settle_s,
                    )
                )
        return cls(steps=steps)

    @classmethod
    def wavelength_intensity_matrix(
        cls,
        wavelengths_nm: list[float],
        drive_points_pct: list[float],
        *,
        dark_pre: bool = True,
        interleave_dark: bool = True,
        light_settle_s: float = 30.0,
        dark_settle_s: float = 60.0,
    ) -> Self:
        """The full wavelength x intensity matrix -- one IV per (wl, pct).

        This is the headline campaign: an IV curve at each wavelength with
        varying intensity. Dark steps are interleaved between lit steps
        (giving dark-pre/lit/dark-post at every point) so the device recovers
        before the next condition.
        """
        steps: list[IlluminationStep] = []
        if dark_pre:
            steps.append(IlluminationStep(label="dark_pre", settle_s=dark_settle_s))
        for wl in wavelengths_nm:
            for pct in drive_points_pct:
                steps.append(
                    IlluminationStep(
                        label=f"{int(wl)}nm_{pct:g}pct",
                        wavelength_nm=wl,
                        intensity_pct=pct,
                        settle_s=light_settle_s,
                    )
                )
                if interleave_dark:
                    steps.append(
                        IlluminationStep(
                            label=f"dark_post_{int(wl)}_{pct:g}pct",
                            settle_s=dark_settle_s,
                        )
                    )
        return cls(steps=steps)

    @classmethod
    def intensity_series_per_wavelength(
        cls,
        wavelengths_nm: list[float],
        drive_points_pct: list[float],
        *,
        dark_settle_s: float = 60.0,
        light_settle_s: float = 30.0,
        inter_light_delay_s: float = 0.0,
        post_series_delay_s: float = 0.0,
        inter_wavelength_delay_s: float = 0.0,
    ) -> Self:
        """Grouped intensity series: dark-pre, all lit levels, dark-post, per λ.

        For each wavelength, in order::

            dark_pre  ->  lit@p0  ->  lit@p1  ->  ...  ->  lit@pN  ->  dark_post

        Unlike :meth:`wavelength_intensity_matrix`, dark is *not* interleaved
        between levels -- the lit sweeps run as a contiguous series, bracketed
        by a single dark reference before and after.

        Timing knobs map onto per-step ``post_delay_s``:

        - ``inter_light_delay_s`` -- waited after each lit sweep before the next
          intensity level (e.g. after 1 %, before 3 %).
        - ``post_series_delay_s`` -- waited after the *last* lit level, before
          the dark-post reference.
        - ``inter_wavelength_delay_s`` -- waited after dark-post, before the
          next wavelength's dark-pre (zero after the final wavelength).
        - ``light_settle_s`` / ``dark_settle_s`` -- dwell *after* applying the
          light state, before that step's sweep.
        """
        steps: list[IlluminationStep] = []
        last_wl_index = len(wavelengths_nm) - 1
        for wi, wl in enumerate(wavelengths_nm):
            steps.append(
                IlluminationStep(
                    label=f"{int(wl)}nm_dark_pre",
                    settle_s=dark_settle_s,
                    post_delay_s=0.0,
                )
            )
            last_level_index = len(drive_points_pct) - 1
            for li, pct in enumerate(drive_points_pct):
                is_last_level = li == last_level_index
                steps.append(
                    IlluminationStep(
                        label=f"{int(wl)}nm_{pct:g}pct",
                        wavelength_nm=wl,
                        intensity_pct=pct,
                        settle_s=light_settle_s,
                        post_delay_s=(
                            post_series_delay_s if is_last_level else inter_light_delay_s
                        ),
                    )
                )
            steps.append(
                IlluminationStep(
                    label=f"{int(wl)}nm_dark_post",
                    settle_s=dark_settle_s,
                    post_delay_s=(
                        0.0 if wi == last_wl_index else inter_wavelength_delay_s
                    ),
                )
            )
        return cls(steps=steps)


__all__ = ["IlluminationSequence", "IlluminationStep"]
