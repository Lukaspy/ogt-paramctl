"""FLEX wire-protocol helpers: command formatting and response parsing.

Kept separate from ``flex.py`` so the parser is exercised by plain unit
tests with no PyVISA / no instrument involvement. The transport-side glue
(actually opening a resource and reading bytes) lives in ``flex.py``.

Reference: Agilent 4155B/4156B Programmer's Guide, Edition 4
(``manuals/4155and4156b_progguide.pdf``), Chapter 3 "FLEX Command
Programming". The ASCII output format used here is ``FMT 1,1`` — ASCII
with a per-field status header, source data enabled.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models.channel import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    is_smu,
)
from ..models.measurement import (
    SweepDirection,
    SweepMeasurement,
    SweepScale,
)
from ..models.setup import Setup

#: SMU and (future) other-unit channel-number mapping. The 4155/4156 numbers
#: SMU1..SMU4 as 1..4 in FLEX. VSU/VMU/GNDU mappings are family-dependent and
#: not yet exercised by M0 step 4 — extend when those channels are in scope.
_FLEX_CHANNEL_NUMBER: dict[ChannelId, int] = {
    ChannelId.SMU1: 1,
    ChannelId.SMU2: 2,
    ChannelId.SMU3: 3,
    ChannelId.SMU4: 4,
}

#: Reverse map used by the response parser: channel letter -> ChannelId.
#: Per the Programmer's Guide, A..D denote SMU1..SMU4 in the FMT 1 header.
_FLEX_CHANNEL_LETTER: dict[str, ChannelId] = {
    "A": ChannelId.SMU1,
    "B": ChannelId.SMU2,
    "C": ChannelId.SMU3,
    "D": ChannelId.SMU4,
}

#: Sweep-mode codes for the WV/WI command's second argument.
_SWEEP_MODE_CODE: dict[tuple[SweepScale, SweepDirection], int] = {
    (SweepScale.LINEAR, SweepDirection.SINGLE): 1,
    (SweepScale.LINEAR, SweepDirection.DOUBLE): 2,
    (SweepScale.LOG10, SweepDirection.SINGLE): 3,
    (SweepScale.LOG10, SweepDirection.DOUBLE): 4,
    (SweepScale.LOG25, SweepDirection.SINGLE): 3,
    (SweepScale.LOG25, SweepDirection.DOUBLE): 4,
    (SweepScale.LOG50, SweepDirection.SINGLE): 3,
    (SweepScale.LOG50, SweepDirection.DOUBLE): 4,
}

_FIELD_WIDTH = 18


class FlexProtocolError(ValueError):
    """Raised when a FLEX response or setup cannot be translated."""


def channel_number(channel_id: ChannelId) -> int:
    """Map a model-level ``ChannelId`` to its FLEX numeric channel index."""
    try:
        return _FLEX_CHANNEL_NUMBER[channel_id]
    except KeyError as exc:
        raise FlexProtocolError(
            f"FLEX driver does not yet support channel {channel_id} "
            "(only SMU1..SMU4 are mapped)."
        ) from exc


def expected_value_count(sweep: SweepMeasurement) -> int:
    """How many ASCII data fields ``RMD?`` will return for the run.

    With FMT 1,1 (source data on), each sweep point yields:
      - one measurement reading on the VAR1 channel, plus
      - one source-data echo of the swept value
    -> 2 fields per point. DOUBLE direction has ``2*N - 1`` points.
    """
    n = sweep.var1.points
    if sweep.var1.direction is SweepDirection.DOUBLE:
        n = 2 * n - 1
    return 2 * n


def build_setup_commands(setup: Setup) -> list[str]:
    """Build the FLEX command sequence that configures the instrument.

    The caller is expected to issue ``XE`` after these. ``CL`` (channel
    cleanup) is the caller's responsibility too — it runs after data is
    read, not as part of setup.

    Args:
        setup: A validated, sweep-mode ``Setup``.

    Returns:
        Ordered list of one-line FLEX commands. Each entry is a single
        statement to be sent to the instrument verbatim.

    Raises:
        FlexProtocolError: For unsupported channels, modes, or measurement
            kinds in this milestone of the FLEX driver.
    """
    if not isinstance(setup.measurement, SweepMeasurement):
        raise FlexProtocolError(
            "FLEX driver currently only supports sweep measurements "
            f"(got {type(setup.measurement).__name__})."
        )
    sweep = setup.measurement

    enabled = [c for c in setup.channels if c.mode is not ChannelMode.DISABLED]
    if not enabled:
        raise FlexProtocolError("setup has no enabled channels.")

    for ch in enabled:
        if not is_smu(ch.channel_id):
            raise FlexProtocolError(
                f"FLEX driver M0 only supports SMU channels; setup uses "
                f"{ch.channel_id}. Extend channel_number() and this guard when "
                "VSU/VMU support lands."
            )

    var1 = next(c for c in setup.channels if c.function is ChannelFunction.VAR1)
    if var1.mode not in (ChannelMode.V_SOURCE, ChannelMode.I_SOURCE):
        raise FlexProtocolError(
            f"VAR1 channel {var1.channel_id} must be V_SOURCE or I_SOURCE "
            f"(got {var1.mode})."
        )

    cmds: list[str] = []
    cmds.append("US")            # enter FLEX command mode
    cmds.append("FMT 1,1")        # ASCII with source data echo
    cmds.append(_cn_command(enabled))
    cmds.append(_sweep_command(var1, sweep))
    cmds.extend(_const_source_commands(setup, var1))
    cmds.append(f"WT {_fmt(sweep.hold_time)},{_fmt(sweep.delay_time)}")
    cmds.append(f"MM 2,{channel_number(var1.channel_id)}")
    return cmds


def _cn_command(channels: list[ChannelConfig]) -> str:
    nums = [str(channel_number(c.channel_id)) for c in channels]
    return "CN " + ",".join(nums)


def _sweep_command(var1: ChannelConfig, sweep: SweepMeasurement) -> str:
    cmd = "WI" if var1.mode is ChannelMode.I_SOURCE else "WV"
    mode_code = _SWEEP_MODE_CODE[(sweep.var1.scale, sweep.var1.direction)]
    parts = [
        str(channel_number(var1.channel_id)),
        str(mode_code),
        "0",  # range = auto
        _fmt(sweep.var1.start),
        _fmt(sweep.var1.stop),
        str(sweep.var1.points),
    ]
    if var1.compliance is not None:
        parts.append(_fmt(var1.compliance))
    return f"{cmd} " + ",".join(parts)


def _const_source_commands(setup: Setup, var1: ChannelConfig) -> list[str]:
    out: list[str] = []
    for ch in setup.channels:
        if ch.channel_id == var1.channel_id:
            continue
        if ch.mode not in (ChannelMode.V_SOURCE, ChannelMode.I_SOURCE):
            continue
        cmd = "DV" if ch.mode is ChannelMode.V_SOURCE else "DI"
        parts = [str(channel_number(ch.channel_id)), "0", _fmt(ch.source_value)]
        if ch.compliance is not None:
            parts.append(_fmt(ch.compliance))
        out.append(f"{cmd} " + ",".join(parts))
    return out


def _fmt(value: float) -> str:
    """Format a numeric value as the 4155 expects: short scientific."""
    if value == 0:
        return "0"
    return f"{value:.6E}"


@dataclass(frozen=True, slots=True)
class FlexField:
    """One parsed field from a FMT 1 response."""

    status: str
    channel: ChannelId
    is_source: bool
    is_voltage: bool
    value: float


def parse_field(field: str) -> FlexField:
    """Parse a single 18-char FMT 1 field into a structured value.

    Layout: ``<3-char status><1-char channel><1-char type><13-char number>``.
    Channel letters A..D map to SMU1..SMU4. Type letters: uppercase
    (``V``/``I``) is a measurement; lowercase (``v``/``i``) is the
    source-data echo.

    Args:
        field: One field of exactly 18 characters (the comma separator must
            already be stripped).

    Raises:
        FlexProtocolError: If the field is the wrong length or has an
            unrecognised channel/type letter.
    """
    if len(field) != _FIELD_WIDTH:
        raise FlexProtocolError(
            f"expected {_FIELD_WIDTH}-char FLEX field, got {len(field)}: {field!r}"
        )
    status = field[0:3]
    chan_letter = field[3]
    type_letter = field[4]
    numeric = field[5:]

    if chan_letter not in _FLEX_CHANNEL_LETTER:
        raise FlexProtocolError(f"unknown channel letter {chan_letter!r} in {field!r}")
    if type_letter not in {"V", "I", "v", "i"}:
        raise FlexProtocolError(f"unknown type letter {type_letter!r} in {field!r}")

    try:
        value = float(numeric)
    except ValueError as exc:
        raise FlexProtocolError(f"non-numeric value in field {field!r}") from exc

    return FlexField(
        status=status,
        channel=_FLEX_CHANNEL_LETTER[chan_letter],
        is_source=type_letter.islower(),
        is_voltage=type_letter in {"V", "v"},
        value=value,
    )


def parse_response(response: str) -> list[FlexField]:
    """Split a comma-separated FMT 1 response and parse each field."""
    fields = response.split(",")
    return [parse_field(f) for f in fields]


__all__ = [
    "FlexField",
    "FlexProtocolError",
    "build_setup_commands",
    "channel_number",
    "expected_value_count",
    "parse_field",
    "parse_response",
]
