"""Integration tests for the photo-IV campaign window (in-GUI instruments)."""
from __future__ import annotations

from pathlib import Path

from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepMeasurement,
    SweepRange,
)
from paramctl.ui.photoiv_window import PhotoIvWindow


def _setup(points: int = 5) -> Setup:
    return Setup(
        name="IV smoke",
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10e-3,
                label="Device",
            ),
        ],
        measurement=SweepMeasurement(var1=SweepRange(start=-1.0, stop=1.0, points=points)),
    )


def _mock_window(qtbot, points: int = 5) -> PhotoIvWindow:
    """Window with the mock analyzer pre-selected, connected, and mock light."""
    win = PhotoIvWindow(_setup(points=points), preselect_mock=True)
    qtbot.addWidget(win)
    qtbot.waitUntil(
        lambda: win._driver is not None and win._driver.is_connected, timeout=5000
    )
    return win


def _zero_timing(win: PhotoIvWindow) -> None:
    win._light_settle.setValue(0.0)
    win._dark_settle.setValue(0.0)
    win._delay_spin.setValue(0.0)
    win._inter_light_delay.setValue(0.0)
    win._post_series_delay.setValue(0.0)
    win._inter_wl_delay.setValue(0.0)


def test_preselect_mock_connects_and_selects_mock_light(qtbot) -> None:
    win = _mock_window(qtbot)
    assert "MOCK" in win._analyzer_status.text()
    assert win._light_combo.currentText() == "Mock light"


def test_single_curve_matrix_writes_one_csv_per_step(qtbot, tmp_path: Path) -> None:
    win = _mock_window(qtbot)

    win._mode_combo.setCurrentIndex(win._mode_combo.findData("matrix"))
    win._dual_check.setChecked(False)
    win._outdir_edit.setText(str(tmp_path))
    win._wl_checks[385.0].setChecked(True)
    win._intensity_edit.setText("100")
    _zero_timing(win)
    win._on_generate_sequence()

    # dark_pre, 385nm_100pct, dark_post -> 3 staged measurements, 1 curve each.
    assert win._queue.count() == 3
    assert win._sequence is not None and len(win._sequence) == 3

    win._on_run()
    qtbot.waitUntil(lambda: win._thread is None, timeout=10_000)

    written = sorted(p.name for p in tmp_path.glob("*.csv"))
    assert len(written) == 3
    assert any("385nm_100pct" in name and "to+" not in name for name in written)
    assert any("dark_pre" in name for name in written)
    markers = [win._queue.item(i).text()[0] for i in range(win._queue.count())]
    assert markers == ["✓", "✓", "✓"]


def test_series_dual_polarity_writes_two_curves_per_step(qtbot, tmp_path: Path) -> None:
    win = _mock_window(qtbot)

    win._mode_combo.setCurrentIndex(win._mode_combo.findData("series"))
    win._dual_check.setChecked(True)
    win._dual_v.setValue(7.0)
    win._dual_points.setValue(5)
    win._outdir_edit.setText(str(tmp_path))
    win._wl_checks[385.0].setChecked(True)
    win._intensity_edit.setText("1, 3")
    _zero_timing(win)
    win._on_generate_sequence()

    # dark_pre, 1pct, 3pct, dark_post -> 4 measurements, 2 curves each = 8 sweeps.
    assert win._queue.count() == 4
    assert win._sequence is not None and len(win._sequence) == 4

    win._on_run()
    qtbot.waitUntil(lambda: win._thread is None, timeout=15_000)

    written = sorted(p.name for p in tmp_path.glob("*.csv"))
    assert len(written) == 8
    assert sum("0to+7V" in n for n in written) == 4
    assert sum("0to-7V" in n for n in written) == 4
    assert any("385nm_1pct" in n for n in written)
    assert any("385nm_3pct" in n for n in written)
    assert any("dark_pre" in n for n in written)
    assert any("dark_post" in n for n in written)

    markers = [win._queue.item(i).text()[0] for i in range(win._queue.count())]
    assert markers == ["✓", "✓", "✓", "✓"]


def test_reverse_order_generates_ir_first(qtbot) -> None:
    win = _mock_window(qtbot)

    win._wl_checks[385.0].setChecked(True)
    win._wl_checks[850.0].setChecked(True)
    win._intensity_edit.setText("100")
    win._reverse_check.setChecked(True)
    win._on_generate_sequence()

    assert win._sequence is not None
    lit = [s.wavelength_nm for s in win._sequence.steps if not s.is_dark]
    assert lit == [850.0, 385.0]

    # And unchecked -> ascending (UV first), the previous default.
    win._reverse_check.setChecked(False)
    win._on_generate_sequence()
    assert win._sequence is not None
    lit = [s.wavelength_nm for s in win._sequence.steps if not s.is_dark]
    assert lit == [385.0, 850.0]


def test_run_without_connect_is_rejected(qtbot) -> None:
    win = PhotoIvWindow(_setup())  # no preselect — nothing connected
    qtbot.addWidget(win)
    win._wl_checks[385.0].setChecked(True)
    win._on_generate_sequence()
    win._on_run()
    assert win._thread is None  # refused before starting anything


def test_run_with_pxi_light_but_no_bitfile_is_rejected(qtbot) -> None:
    win = _mock_window(qtbot)
    win._light_combo.setCurrentText("PXI FPGA LED source")
    win._bitfile_edit.setText("")
    win._wl_checks[385.0].setChecked(True)
    _zero_timing(win)
    win._on_generate_sequence()
    win._on_run()
    # led_driver would silently run its own mock backend -> must refuse.
    assert win._thread is None


def test_run_without_sequence_is_rejected(qtbot) -> None:
    win = _mock_window(qtbot)
    win._on_run()  # no sequence generated yet
    assert win._thread is None
