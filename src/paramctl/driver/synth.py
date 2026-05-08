"""Synthetic-data helpers used by ``MockDriver`` to produce plausible curves.

The math here is deliberately rough — the goal is "looks right on a plot",
not "physically accurate." A test engineer skimming a plot of mock data
should see something that resembles the real thing; a measurement engineer
should not mistake it for real data.
"""
from __future__ import annotations

import math
import random

from ..models.channel import ChannelConfig, ChannelFunction, ChannelId, ChannelMode
from ..models.measurement import (
    SweepDirection,
    SweepMeasurement,
    SweepRange,
    SweepScale,
)
from ..models.setup import Setup

_VTH_DEFAULT = 0.7
_K_DEFAULT = 5e-4
_LAMBDA_DEFAULT = 0.05
_DIODE_IS = 1e-12
_DIODE_VT = 0.02585  # kT/q at 300 K


def sweep_points(rng: SweepRange) -> list[float]:
    """Materialise the sweep variable values implied by a ``SweepRange``.

    Honours scale (linear vs log decade variants) and direction (single
    forward, or forward-then-reverse with the apex sample shared).

    Returns:
        Ordered list of source values; length equals ``rng.points`` for
        SINGLE direction, ``2 * rng.points - 1`` for DOUBLE.
    """
    if rng.scale is SweepScale.LINEAR:
        step = (rng.stop - rng.start) / (rng.points - 1)
        forward = [rng.start + step * i for i in range(rng.points)]
    else:
        sign = 1.0 if rng.start > 0 else -1.0
        log_a = math.log10(abs(rng.start))
        log_b = math.log10(abs(rng.stop))
        log_step = (log_b - log_a) / (rng.points - 1)
        forward = [sign * (10 ** (log_a + log_step * i)) for i in range(rng.points)]

    if rng.direction is SweepDirection.SINGLE:
        return forward
    # DOUBLE: forward, then reversed without re-emitting the apex
    return forward + list(reversed(forward[:-1]))


def _mosfet_drain_current(
    vds: float,
    vgs: float,
    vth: float = _VTH_DEFAULT,
    k: float = _K_DEFAULT,
    lam: float = _LAMBDA_DEFAULT,
) -> float:
    """Square-law NMOS Id model with channel-length modulation.

    Three regions:
        - Off (Vgs <= Vth): tiny leakage.
        - Triode/linear (0 <= Vds < Vov): I_d = k*(Vov*Vds - Vds**2/2)*(1 + lam*Vds).
        - Saturation (Vds >= Vov): I_d = (k/2)*Vov**2*(1 + lam*Vds).

    Negative Vds is reflected (treated as the body-diode regime, returning a
    rough negative current). Adequate for a plot; not a calibrated model.
    """
    vov = vgs - vth
    if vov <= 0:
        return 1e-12
    if vds < 0:
        # Body-diode-ish: small negative current that grows with |Vds|.
        return -_mosfet_drain_current(-vds, vgs, vth, k, lam)
    if vds < vov:
        return k * (vov * vds - 0.5 * vds * vds) * (1 + lam * vds)
    return 0.5 * k * vov * vov * (1 + lam * vds)


def _diode_current(v: float, is_sat: float = _DIODE_IS, vt: float = _DIODE_VT) -> float:
    """Shockley diode equation, with overflow guard for huge forward bias."""
    arg = v / vt
    if arg > 60:
        return is_sat * math.exp(60)  # ~1e14 * Is - will be compliance-clamped
    if arg < -60:
        return -is_sat
    return is_sat * (math.exp(arg) - 1.0)


def _add_noise(value: float, *, noise_floor: float, noise_ratio: float) -> float:
    sigma = max(abs(value) * noise_ratio, noise_floor)
    return value + random.gauss(0.0, sigma)


def _gate_constant(setup: Setup, var1_id: ChannelId) -> ChannelConfig | None:
    """Return the first non-VAR1 V-sourcing channel, treated as gate bias.

    Returns ``None`` if the setup has no constant V-source companion — in
    which case the synth falls back to a diode model on the VAR1 channel.
    """
    for ch in setup.channels:
        if (
            ch.channel_id != var1_id
            and ch.mode is ChannelMode.V_SOURCE
            and ch.function is ChannelFunction.CONST
        ):
            return ch
    return None


def synth_readings(
    setup: Setup,
    sweep: SweepMeasurement,
    var1_value: float,
    *,
    noise_floor: float = 1e-12,
    noise_ratio: float = 0.005,
) -> tuple[dict[ChannelId, float], bool]:
    """Compute readings for one sweep step plus a compliance-hit flag.

    Currently models:
        - VAR1 V-sourcing SMU: drain current via MOSFET square-law if a
          companion V-sourcing CONST channel exists (treated as gate); diode
          equation otherwise.
        - VAR1 I-sourcing SMU: voltage across a 1 kΩ load.
        - Companion V-source channels: gate leakage current near zero.
        - Disabled / VMU / GNDU channels: omitted from readings.

    All currents/voltages get clamped to channel compliance and a small
    Gaussian noise term applied for realism. The returned bool is ``True``
    iff the unclamped model output exceeded the VAR1 channel's compliance
    (i.e. the instrument would have hit compliance there).
    """
    var1 = next(c for c in setup.channels if c.function is ChannelFunction.VAR1)
    readings: dict[ChannelId, float] = {}

    if var1.mode is ChannelMode.V_SOURCE:
        gate = _gate_constant(setup, var1.channel_id)
        if gate is not None:
            primary = _mosfet_drain_current(var1_value, gate.source_value)
        else:
            primary = _diode_current(var1_value)
    else:  # I_SOURCE
        primary = var1_value * 1_000.0  # 1 kΩ resistor model -> volts

    clamped, compliance_hit = _clamp_to_compliance(primary, var1.compliance)
    readings[var1.channel_id] = _add_noise(
        clamped, noise_floor=noise_floor, noise_ratio=noise_ratio
    )

    for ch in setup.channels:
        if ch.channel_id == var1.channel_id:
            continue
        if ch.mode is ChannelMode.DISABLED:
            continue
        if ch.mode in (ChannelMode.V_SOURCE, ChannelMode.I_SOURCE):
            companion = _add_noise(0.0, noise_floor=noise_floor, noise_ratio=noise_ratio)
            readings[ch.channel_id] = companion

    # var2 unused for now; M0 only exercises VAR1 sweeps.
    del sweep
    return readings, compliance_hit


def _clamp_to_compliance(
    value: float, compliance: float | None
) -> tuple[float, bool]:
    """Clamp ``value`` to ``±compliance``; second return is ``True`` when clamped."""
    if compliance is None:
        return value, False
    if value > compliance:
        return compliance, True
    if value < -compliance:
        return -compliance, True
    return value, False


__all__ = ["sweep_points", "synth_readings"]
