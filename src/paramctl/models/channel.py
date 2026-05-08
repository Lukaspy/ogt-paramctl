"""Channel-level models: identity, mode, function, and per-channel configuration.

The 4155/4156 channel inventory is fixed (4 SMUs, 2 VSUs, 2 VMUs, GNDU).
A given measurement uses some subset of these channels; each enabled channel
has a mode (V/I source, common, disabled) and a sweep-related function
(VAR1, VAR2, VAR1', or CONST). These models describe *what* a channel does,
not *how* a specific instrument carries it out — instrument-specific FLEX
syntax lives in the driver layer.
"""
from __future__ import annotations

from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChannelId(str, Enum):
    """Physical channel slots on the 4155/4156 instrument front panel."""

    SMU1 = "SMU1"
    SMU2 = "SMU2"
    SMU3 = "SMU3"
    SMU4 = "SMU4"
    VSU1 = "VSU1"
    VSU2 = "VSU2"
    VMU1 = "VMU1"
    VMU2 = "VMU2"
    GNDU = "GNDU"


_SMU_CHANNELS = frozenset(
    {ChannelId.SMU1, ChannelId.SMU2, ChannelId.SMU3, ChannelId.SMU4}
)
_VSU_CHANNELS = frozenset({ChannelId.VSU1, ChannelId.VSU2})
_VMU_CHANNELS = frozenset({ChannelId.VMU1, ChannelId.VMU2})


def is_smu(channel_id: ChannelId) -> bool:
    """True if the channel is a Source/Measure Unit (SMU1..SMU4)."""
    return channel_id in _SMU_CHANNELS


def is_vsu(channel_id: ChannelId) -> bool:
    """True if the channel is a Voltage Source Unit (VSU1..VSU2)."""
    return channel_id in _VSU_CHANNELS


def is_vmu(channel_id: ChannelId) -> bool:
    """True if the channel is a Voltage Monitor Unit (VMU1..VMU2)."""
    return channel_id in _VMU_CHANNELS


class ChannelMode(str, Enum):
    """How a channel is operating during the measurement.

    - ``V_SOURCE`` — channel sources voltage; measures current (SMU only).
    - ``I_SOURCE`` — channel sources current; measures voltage (SMU only).
    - ``COMMON`` — channel is held at common (used by GNDU; also SMUs as
      0V references). VMU monitors are also represented as ``COMMON`` mode
      because they take no source action.
    - ``DISABLED`` — channel is not used in the measurement.
    """

    V_SOURCE = "V_SOURCE"
    I_SOURCE = "I_SOURCE"
    COMMON = "COMMON"
    DISABLED = "DISABLED"


class ChannelFunction(str, Enum):
    """Role a channel plays in the measurement's sweep structure.

    - ``VAR1`` — primary sweep variable (the X axis).
    - ``VAR2`` — secondary sweep variable (yields a family of curves).
    - ``VAR1_PRIME`` — variable linked to ``VAR1`` by ratio + offset.
    - ``CONST`` — channel holds a fixed value during the sweep.

    For passive channels (VMU, GNDU, DISABLED), function is ``CONST`` by
    convention; the engine ignores it.
    """

    VAR1 = "VAR1"
    VAR2 = "VAR2"
    VAR1_PRIME = "VAR1_PRIME"
    CONST = "CONST"


_SOURCE_MODES = frozenset({ChannelMode.V_SOURCE, ChannelMode.I_SOURCE})
_SWEEP_FUNCTIONS = frozenset(
    {ChannelFunction.VAR1, ChannelFunction.VAR2, ChannelFunction.VAR1_PRIME}
)


class ChannelConfig(BaseModel):
    """Configuration for a single instrument channel.

    Attributes:
        channel_id: Which physical channel this configures.
        mode: How the channel sources/measures (or whether it is disabled).
        function: Role in the sweep — sweep variable, link, or constant.
        source_value: Constant value the channel sources when function is
            ``CONST`` and mode is ``V_SOURCE``/``I_SOURCE``. Volts for
            voltage sources, amps for current sources. Ignored otherwise.
        compliance: Safety limit on the measured side: max current when
            sourcing voltage, max voltage when sourcing current. Required
            for source modes; ``None`` for non-sourcing modes.
        label: Optional human label (e.g. ``"Drain"``, ``"Gate"``).
            Surfaced in plot legends and CSV headers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    channel_id: ChannelId
    mode: ChannelMode
    function: ChannelFunction = ChannelFunction.CONST
    source_value: float = 0.0
    compliance: float | None = Field(default=None)
    label: str = ""

    @model_validator(mode="after")
    def _validate_channel_consistency(self) -> Self:
        # Hardware-shaped constraints first: which channel slots can do what.
        if self.channel_id is ChannelId.GNDU and self.mode is not ChannelMode.COMMON:
            raise ValueError("GNDU is always COMMON mode.")

        if self.channel_id in _VMU_CHANNELS and self.mode in _SOURCE_MODES:
            raise ValueError(
                f"{self.channel_id} is a Voltage Monitor Unit; cannot source."
            )

        if self.mode in _SOURCE_MODES and not (
            is_smu(self.channel_id) or self.channel_id in _VSU_CHANNELS
        ):
            raise ValueError(
                f"{self.channel_id} cannot source; only SMU and VSU channels do."
            )

        if self.mode is ChannelMode.I_SOURCE and self.channel_id in _VSU_CHANNELS:
            raise ValueError(
                f"{self.channel_id} is a Voltage Source Unit; I_SOURCE not supported."
            )

        # Function constraints: DISABLED first so its message wins over the
        # generic "function VAR* requires a source mode" check below.
        if self.mode is ChannelMode.DISABLED and self.function is not ChannelFunction.CONST:
            raise ValueError("DISABLED channels cannot have a sweep function.")

        if self.function in _SWEEP_FUNCTIONS and self.mode not in _SOURCE_MODES:
            raise ValueError(
                f"{self.channel_id} has function {self.function} but is not a "
                f"source (mode={self.mode}); only source channels can sweep."
            )

        # Compliance rules. VSUs do not measure, so compliance is meaningless
        # for them; SMUs in a source mode must declare it.
        if (
            self.mode in _SOURCE_MODES
            and is_smu(self.channel_id)
            and self.compliance is None
        ):
            raise ValueError(
                f"{self.channel_id} in {self.mode} requires a compliance value."
            )

        if self.compliance is not None and self.compliance <= 0:
            raise ValueError("compliance must be positive when set.")

        return self


class ChannelLimits(BaseModel):
    """Per-channel safety ceilings enforced by ``Setup`` validation.

    These are an additional layer of defence on top of the instrument's
    own compliance setting: a setup whose source value or compliance
    exceeds these limits is rejected before it ever reaches the driver.

    Attributes:
        max_voltage: Absolute maximum voltage (volts) — applies to both
            source value (when V-sourcing) and compliance (when I-sourcing).
        max_current: Absolute maximum current (amps) — applies to both
            source value (when I-sourcing) and compliance (when V-sourcing).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_voltage: float = Field(gt=0)
    max_current: float = Field(gt=0)


__all__ = [
    "ChannelConfig",
    "ChannelFunction",
    "ChannelId",
    "ChannelLimits",
    "ChannelMode",
    "is_smu",
    "is_vmu",
    "is_vsu",
]
