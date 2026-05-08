"""Unit tests for the SI-prefix formatter and parser."""
from __future__ import annotations

import pytest

from paramctl.util.units import format_si, parse_si


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        (0.0, "A", "0 A"),
        (0.0, "", "0"),
        (1.0, "V", "1 V"),
        (1.5, "V", "1.5 V"),
        (1.5e-3, "A", "1.5 mA"),
        (100e-6, "A", "100 uA"),
        (1e-12, "A", "1 pA"),
        (1.234567e-9, "A", "1.235 nA"),
        (1.5e3, "Hz", "1.5 kHz"),
        (2.5e6, "Hz", "2.5 MHz"),
        (-1.5e-3, "A", "-1.5 mA"),
        (1.0, "", "1"),
        (1e-3, "", "1 m"),
        (1e-3, "s", "1 ms"),
    ],
)
def test_format_si_picks_best_prefix(value: float, unit: str, expected: str) -> None:
    assert format_si(value, unit=unit) == expected


def test_format_si_negative_uses_same_prefix_as_positive() -> None:
    assert format_si(-1.5e-3, unit="A") == "-1.5 mA"


def test_format_si_decimals_respected() -> None:
    assert format_si(1.234567e-3, decimals=3, unit="A") == "1.23 mA"
    assert format_si(1.234567e-3, decimals=5, unit="A") == "1.2346 mA"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1", 1.0),
        ("1.5", 1.5),
        ("1.5e-3", 1.5e-3),
        ("1.5 m", 1.5e-3),
        ("1.5m", 1.5e-3),
        ("1.5 mA", 1.5e-3),
        ("1.5mA", 1.5e-3),
        ("100 u", 100e-6),
        ("100u", 100e-6),
        ("100 uA", 100e-6),
        ("100µ", 100e-6),
        ("100 µA", 100e-6),
        ("1 V", 1.0),
        ("-2.5 m", -2.5e-3),
        ("+1k", 1e3),
        ("2 M", 2e6),
        ("3 G", 3e9),
        ("1 p", 1e-12),
        ("1 f", 1e-15),
        ("1.5e-3 A", 1.5e-3),
    ],
)
def test_parse_si_handles_canonical_forms(text: str, expected: float) -> None:
    assert parse_si(text) == pytest.approx(expected)


@pytest.mark.parametrize("garbage", ["", "abc", "1 X 2", "1 mm m"])
def test_parse_si_rejects_garbage(garbage: str) -> None:
    with pytest.raises(ValueError):
        parse_si(garbage)


def test_format_then_parse_round_trips_at_typical_scales() -> None:
    for value in [0.0, 1.0, 1.5e-3, 100e-6, 25e-9, 1e-12, 5.0, -2.5e-3, 1e3]:
        text = format_si(value, unit="A")
        assert parse_si(text) == pytest.approx(value, rel=1e-3)


def test_parse_distinguishes_milli_and_mega_by_case() -> None:
    assert parse_si("1 m") == pytest.approx(1e-3)
    assert parse_si("1 M") == pytest.approx(1e6)


def test_format_si_zero_with_no_unit_returns_bare_zero() -> None:
    assert format_si(0.0) == "0"
