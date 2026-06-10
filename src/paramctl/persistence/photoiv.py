"""Per-curve CSV output for a photo-IV campaign.

Each illumination step produces one IV curve, written as a standard paramctl
trace CSV (so it loads back through :func:`read_run_csv`) with the
illumination state recorded in the comment header. Filenames key on the
device id and the step label::

    IV_<device>_<step-label>_<YYYYMMDD_HHMMSS>.csv
    IV_dev42_385nm_50pct_20260610_142233.csv
    IV_dev42_dark_pre_20260610_142051.csv
"""
from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path

from ..models.campaign import PhotoIvCampaign
from ..models.illumination import IlluminationStep
from ..models.results import Sample
from .data import write_run_csv

_UNSAFE = re.compile(r"[^0-9A-Za-z._+-]+")


def _slug(text: str) -> str:
    """Collapse anything filename-unsafe to underscores."""
    return _UNSAFE.sub("_", text.strip()) or "unknown"


def photoiv_filename(
    campaign: PhotoIvCampaign,
    step: IlluminationStep,
    timestamp: _dt.datetime | None = None,
    curve_label: str = "",
) -> str:
    """Build the per-curve filename for one illumination step.

    ``curve_label`` (e.g. ``"0to+7V"``) is appended when a step runs more than
    one sweep range, so the two polarity curves get distinct files. It is
    empty for the single-sweep default, leaving those filenames unchanged.
    """
    when = timestamp or _dt.datetime.now()
    stamp = when.strftime("%Y%m%d_%H%M%S")
    device = _slug(campaign.device_id or "unknown")
    label = _slug(step.label)
    curve = f"_{_slug(curve_label)}" if curve_label else ""
    return f"IV_{device}_{label}{curve}_{stamp}.csv"


def illumination_metadata(
    campaign: PhotoIvCampaign,
    step: IlluminationStep,
    *,
    curve_label: str = "",
    led_current_ma: float | None = None,
    optical_power_mw: float | None = None,
) -> dict[str, str]:
    """Assemble the comment-header metadata for one curve."""
    meta: dict[str, str] = {
        "campaign_device_id": campaign.device_id,
        "substrate_type": campaign.substrate_type,
        "illumination_label": step.label,
        "is_dark": str(step.is_dark),
        "wavelength_nm": "dark" if step.is_dark else f"{step.wavelength_nm}",
        "intensity_pct": f"{step.intensity_pct}",
        "settle_s": f"{step.settle_s}",
    }
    if curve_label:
        meta["curve_range"] = curve_label
    if campaign.notes:
        meta["notes"] = campaign.notes
    if led_current_ma is not None:
        meta["led_current_ma"] = f"{led_current_ma}"
    if optical_power_mw is not None:
        meta["optical_power_mw"] = f"{optical_power_mw}"
    return meta


def write_campaign_curve(
    output_dir: Path | str,
    campaign: PhotoIvCampaign,
    step: IlluminationStep,
    samples: list[Sample],
    *,
    curve_label: str = "",
    timestamp: _dt.datetime | None = None,
    led_current_ma: float | None = None,
    optical_power_mw: float | None = None,
) -> Path:
    """Write one curve to ``output_dir`` and return the path.

    Args:
        output_dir: Destination folder; created if missing.
        campaign: The running campaign (supplies device id, notes).
        step: The illumination step that produced this curve.
        samples: The sweep samples for this curve.
        curve_label: Range tag for a multi-sweep step (e.g. ``"0to+7V"``);
            empty for the single-sweep default.
        timestamp: Filename timestamp; defaults to now.
        led_current_ma: Best-effort actual drive current, if the source
            reported it (informational).
        optical_power_mw: Calibration-predicted optical power, if available.

    Returns:
        The path written.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / photoiv_filename(campaign, step, timestamp, curve_label)
    meta = illumination_metadata(
        campaign,
        step,
        curve_label=curve_label,
        led_current_ma=led_current_ma,
        optical_power_mw=optical_power_mw,
    )
    write_run_csv(path, campaign.base_setup, samples, extra_metadata=meta)
    return path


__all__ = [
    "illumination_metadata",
    "photoiv_filename",
    "write_campaign_curve",
]
