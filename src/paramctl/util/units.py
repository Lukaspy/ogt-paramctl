"""SI-prefix-aware number formatting and parsing.

Designed for instrument values that span 15 orders of magnitude
(femtoamps to amps, microvolts to kilovolts). Display picks the prefix
that keeps the scaled value in the ``[1, 1000)`` range; parsing accepts
prefixes with or without spaces and an optional trailing unit (which is
ignored — the field tells the parser what unit it expects).

Case is significant. ``m`` is milli (1e-3); ``M`` is mega (1e6).
``u`` and ``µ`` both mean micro (1e-6).
"""
from __future__ import annotations

import re

#: Ordered from smallest to largest. The empty-prefix entry is the
#: identity. Add ``a`` (1e-18) and ``T`` (1e12) only when an instrument
#: range needs them.
SI_PREFIXES: tuple[tuple[str, float], ...] = (
    ("f", 1e-15),
    ("p", 1e-12),
    ("n", 1e-9),
    ("u", 1e-6),
    ("m", 1e-3),
    ("", 1.0),
    ("k", 1e3),
    ("M", 1e6),
    ("G", 1e9),
)

# Lookup for the parser. ``µ`` is normalised to ``u`` before lookup so
# both the ASCII and the actual micro symbol parse identically.
_PREFIX_TO_MULTIPLIER: dict[str, float] = {p: m for p, m in SI_PREFIXES}

_NUMBER_RE = re.compile(
    r"""
    ^\s*
    (?P<num>[-+]?\d+\.?\d*(?:[eE][-+]?\d+)?)   # signed decimal, optional exponent
    \s*
    (?P<prefix>[fpnumkMG])?                     # optional SI prefix (case sensitive)
    \s*
    (?P<unit>[A-Za-z]+)?                        # optional unit suffix (ignored)
    \s*$
    """,
    re.VERBOSE,
)


def format_si(value: float, *, decimals: int = 4, unit: str = "") -> str:
    """Format ``value`` with the SI prefix that keeps the mantissa in [1, 1000).

    Args:
        value: Value to format, in SI base units.
        decimals: Significant digits for the mantissa.
        unit: Unit suffix appended after the prefix (e.g. ``"A"`` -> ``"1 mA"``).

    Returns:
        Formatted string. ``0`` always renders as ``"0 <unit>"``; very large
        or very small magnitudes outside the prefix range fall back to
        scientific notation on the largest available prefix.
    """
    if value == 0 or not _is_finite(value):
        return f"{value:g} {unit}".rstrip()

    prefix, multiplier = _best_prefix(value)
    scaled = value / multiplier
    suffix = f"{prefix}{unit}".strip()
    if not suffix:
        return f"{scaled:.{decimals}g}"
    return f"{scaled:.{decimals}g} {suffix}"


def parse_si(text: str) -> float:
    """Parse a number with optional SI prefix and unit suffix.

    Accepts forms like ``"1"``, ``"1.5"``, ``"1.5e-3"``, ``"1.5m"``,
    ``"1.5 mA"``, ``"100 u"``, ``"100µ"``. The unit suffix is ignored;
    the caller's field knows what unit it wants.

    Raises:
        ValueError: If the input does not match a recognised number form.
    """
    normalised = text.replace("µ", "u").replace("μ", "u")
    match = _NUMBER_RE.match(normalised)
    if match is None:
        raise ValueError(f"cannot parse SI value: {text!r}")
    number = float(match.group("num"))
    prefix = match.group("prefix") or ""
    multiplier = _PREFIX_TO_MULTIPLIER[prefix]
    return number * multiplier


def _best_prefix(value: float) -> tuple[str, float]:
    abs_value = abs(value)
    candidates = [(p, m) for p, m in SI_PREFIXES if abs_value >= m]
    if not candidates:
        # Smaller than the smallest prefix; render with the smallest one.
        return SI_PREFIXES[0]
    return max(candidates, key=lambda pm: pm[1])


def _is_finite(x: float) -> bool:
    # math.isfinite without importing math at module top.
    return x == x and x not in (float("inf"), float("-inf"))


__all__ = ["SI_PREFIXES", "format_si", "parse_si"]
