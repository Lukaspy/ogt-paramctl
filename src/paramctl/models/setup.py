"""The top-level ``Setup`` model: the full description of a measurement run.

A ``Setup`` is what gets serialised to YAML, what the engine consumes, and
what the UI edits. It is deliberately driver-agnostic — the same setup
should produce equivalent measurements on a 4155B, 4156C, or (future)
B1500A. Anything genuinely 4155-specific belongs in the driver, not here.
"""
from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .channel import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelLimits,
    ChannelMode,
)
from .measurement import (
    MeasurementMode,
    SamplingMeasurement,
    SpotMeasurement,
    SweepMeasurement,
)

CURRENT_SCHEMA_VERSION: Literal[1] = 1
"""Bump alongside any breaking change to ``Setup`` and add a migration."""


class Setup(BaseModel):
    """Complete measurement specification — channels + mode + safety.

    Attributes:
        schema_version: Pinned to ``1``. Bumping requires a migration.
        name: Human label for the setup (shown in the UI title bar).
        notes: Free-form notes saved alongside the setup.
        channels: One ``ChannelConfig`` per used channel. Channels not
            listed are treated as ``DISABLED``.
        measurement: Discriminated union — sweep, sampling, or spot.
        safety_ceilings: Per-channel absolute caps. A setup whose source
            value or compliance exceeds the ceiling is rejected here,
            before reaching the driver.
        resource_string: Last-used VISA resource string. Optional;
            stored for convenience but never required to load a setup.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = CURRENT_SCHEMA_VERSION
    name: str = ""
    notes: str = ""
    channels: list[ChannelConfig] = Field(min_length=1)
    measurement: MeasurementMode
    safety_ceilings: dict[ChannelId, ChannelLimits] = Field(default_factory=dict)
    resource_string: str | None = None

    @model_validator(mode="after")
    def _validate_setup(self) -> Self:
        self._check_unique_channels()
        self._check_function_consistency()
        self._check_safety_ceilings()
        return self

    def _check_unique_channels(self) -> None:
        seen: set[ChannelId] = set()
        for ch in self.channels:
            if ch.channel_id in seen:
                raise ValueError(f"duplicate channel_id in setup: {ch.channel_id}")
            seen.add(ch.channel_id)

    def _check_function_consistency(self) -> None:
        var1_channels = [c for c in self.channels if c.function is ChannelFunction.VAR1]
        var2_channels = [c for c in self.channels if c.function is ChannelFunction.VAR2]
        var1p_channels = [
            c for c in self.channels if c.function is ChannelFunction.VAR1_PRIME
        ]

        if isinstance(self.measurement, SweepMeasurement):
            if len(var1_channels) != 1:
                raise ValueError(
                    f"sweep requires exactly one VAR1 channel; got {len(var1_channels)}"
                )
            if self.measurement.var2 is None and var2_channels:
                raise ValueError(
                    "channel(s) tagged VAR2 but no var2 sweep range configured."
                )
            if self.measurement.var2 is not None and len(var2_channels) != 1:
                raise ValueError(
                    f"var2 sweep configured but {len(var2_channels)} VAR2 channels found; "
                    "expected exactly one."
                )
            if self.measurement.var1_prime is None and var1p_channels:
                raise ValueError(
                    "channel(s) tagged VAR1_PRIME but no var1_prime link configured."
                )
            if self.measurement.var1_prime is not None and len(var1p_channels) != 1:
                raise ValueError(
                    f"var1_prime configured but {len(var1p_channels)} VAR1_PRIME channels "
                    "found; expected exactly one."
                )
        elif isinstance(self.measurement, SamplingMeasurement | SpotMeasurement):
            for tag, channels in (
                ("VAR1", var1_channels),
                ("VAR2", var2_channels),
                ("VAR1_PRIME", var1p_channels),
            ):
                if channels:
                    raise ValueError(
                        f"{type(self.measurement).__name__} cannot have channels tagged "
                        f"{tag}; tag them CONST instead."
                    )

    def _check_safety_ceilings(self) -> None:
        for channel in self.channels:
            limits = self.safety_ceilings.get(channel.channel_id)
            if limits is None:
                continue
            self._enforce_channel_limits(channel, limits)

    @staticmethod
    def _enforce_channel_limits(
        channel: ChannelConfig, limits: ChannelLimits
    ) -> None:
        if channel.mode is ChannelMode.V_SOURCE:
            if abs(channel.source_value) > limits.max_voltage:
                raise ValueError(
                    f"{channel.channel_id} source value "
                    f"{channel.source_value} V exceeds ceiling {limits.max_voltage} V"
                )
            if (
                channel.compliance is not None
                and channel.compliance > limits.max_current
            ):
                raise ValueError(
                    f"{channel.channel_id} compliance "
                    f"{channel.compliance} A exceeds ceiling {limits.max_current} A"
                )
        elif channel.mode is ChannelMode.I_SOURCE:
            if abs(channel.source_value) > limits.max_current:
                raise ValueError(
                    f"{channel.channel_id} source value "
                    f"{channel.source_value} A exceeds ceiling {limits.max_current} A"
                )
            if (
                channel.compliance is not None
                and channel.compliance > limits.max_voltage
            ):
                raise ValueError(
                    f"{channel.channel_id} compliance "
                    f"{channel.compliance} V exceeds ceiling {limits.max_voltage} V"
                )


__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "Setup",
]
