"""Unit tests for the illumination models and sequence builders."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from paramctl.models import IlluminationSequence, IlluminationStep


def test_dark_step_must_have_zero_intensity() -> None:
    IlluminationStep(label="dark_pre")  # ok: defaults to 0
    with pytest.raises(ValidationError):
        IlluminationStep(label="bad_dark", wavelength_nm=None, intensity_pct=10.0)


def test_intensity_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        IlluminationStep(label="too_bright", wavelength_nm=385.0, intensity_pct=150.0)


def test_is_dark_flag() -> None:
    assert IlluminationStep(label="d").is_dark is True
    assert IlluminationStep(label="l", wavelength_nm=385.0, intensity_pct=5.0).is_dark is False


def test_intensity_series_interleaves_dark() -> None:
    seq = IlluminationSequence.intensity_series(385.0, [25.0, 50.0, 100.0])
    labels = [s.label for s in seq.steps]
    # dark_pre, then (lit, dark_post) per level.
    assert labels[0] == "dark_pre"
    assert len(seq) == 1 + 2 * 3
    lit = [s for s in seq.steps if not s.is_dark]
    assert [s.intensity_pct for s in lit] == [25.0, 50.0, 100.0]
    assert all(s.wavelength_nm == 385.0 for s in lit)


def test_matrix_covers_every_wavelength_and_intensity() -> None:
    wls = [385.0, 530.0]
    pcts = [50.0, 100.0]
    seq = IlluminationSequence.wavelength_intensity_matrix(wls, pcts)
    lit = [s for s in seq.steps if not s.is_dark]
    assert len(lit) == len(wls) * len(pcts)
    seen = {(s.wavelength_nm, s.intensity_pct) for s in lit}
    assert seen == {(385.0, 50.0), (385.0, 100.0), (530.0, 50.0), (530.0, 100.0)}
    # dark interleaved: one dark_pre + one dark_post per lit step.
    assert sum(1 for s in seq.steps if s.is_dark) == 1 + len(lit)


def test_sequence_requires_at_least_one_step() -> None:
    with pytest.raises(ValidationError):
        IlluminationSequence(steps=[])


def test_per_wavelength_series_groups_dark_pre_levels_dark_post() -> None:
    seq = IlluminationSequence.intensity_series_per_wavelength(
        [385.0, 530.0], [1.0, 3.0, 100.0]
    )
    # Per wavelength: dark_pre + 3 lit + dark_post = 5; two wavelengths = 10.
    assert len(seq) == 2 * 5
    labels = [s.label for s in seq.steps]
    assert labels[:5] == [
        "385nm_dark_pre", "385nm_1pct", "385nm_3pct", "385nm_100pct", "385nm_dark_post",
    ]
    # No dark interleaved between the lit levels.
    assert all(not s.is_dark for s in seq.steps[1:4])


def test_per_wavelength_series_assigns_distinct_delays() -> None:
    seq = IlluminationSequence.intensity_series_per_wavelength(
        [385.0, 530.0],
        [1.0, 3.0, 100.0],
        inter_light_delay_s=5.0,
        post_series_delay_s=120.0,
        inter_wavelength_delay_s=30.0,
    )
    lit_385 = [s for s in seq.steps if not s.is_dark and s.wavelength_nm == 385.0]
    # Between levels -> inter_light_delay; after the last level -> post_series_delay.
    assert [s.post_delay_s for s in lit_385] == [5.0, 5.0, 120.0]
    dark_posts = [s for s in seq.steps if s.label.endswith("dark_post")]
    # First wavelength's dark_post waits inter_wavelength_delay; the last is 0.
    assert dark_posts[0].post_delay_s == 30.0
    assert dark_posts[1].post_delay_s == 0.0
