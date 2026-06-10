"""Integration tests for the photo-IV campaign window (in-GUI instruments)."""
from __future__ import annotations

from pathlib import Path

from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepDirection,
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


def test_dual_polarity_inherits_double_sweep_direction(qtbot, tmp_path: Path) -> None:
    win = _mock_window(qtbot)

    # Direction lives in the base editor's Sweep panel; dual-polarity ranges
    # must inherit it instead of resetting to SINGLE.
    sweep_panel = win._editor._sweep
    sweep_panel._direction.setCurrentIndex(
        sweep_panel._direction.findData(SweepDirection.DOUBLE)
    )
    win._mode_combo.setCurrentIndex(win._mode_combo.findData("matrix"))
    win._interleave_check.setChecked(False)
    win._dual_check.setChecked(True)
    win._dual_points.setValue(5)
    win._outdir_edit.setText(str(tmp_path))
    win._wl_checks[385.0].setChecked(True)
    win._intensity_edit.setText("100")
    _zero_timing(win)
    win._on_generate_sequence()

    campaign = win._build_campaign()
    assert campaign is not None and campaign.sweep_ranges is not None
    assert all(r.direction is SweepDirection.DOUBLE for r in campaign.sweep_ranges)

    win._on_run()
    qtbot.waitUntil(lambda: win._thread is None, timeout=10_000)

    # 2 polarities per step; every curve has 2*points-1 rows (retrace).
    assert win._sequence is not None
    written = sorted(tmp_path.glob("*.csv"))
    assert len(written) == 2 * len(win._sequence)
    for path in written:
        rows = [
            line
            for line in path.read_text().splitlines()
            if line and not line.startswith("#")
        ]
        assert len(rows) - 1 == 9  # column header + (2 * 5 - 1) samples


def _combo_items(win: PhotoIvWindow) -> list[str]:
    return [win._resource_combo.itemText(i) for i in range(win._resource_combo.count())]


def test_refresh_discovers_off_thread_and_keeps_selection(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        "paramctl.ui.photoiv_workers.list_resources",
        lambda: ["GPIB0::15::INSTR", "GPIB0::INTFC"],
    )
    win = PhotoIvWindow(_setup())
    qtbot.addWidget(win)
    win._resource_combo.setCurrentText("GPIB0::15::INSTR")  # typed by hand

    win._on_refresh_resources()
    assert not win._refresh_btn.isEnabled()  # busy while discovery is in flight
    qtbot.waitUntil(lambda: win._disc_thread is None, timeout=5000)

    assert _combo_items(win) == ["Mock analyzer", "GPIB0::15::INSTR", "GPIB0::INTFC"]
    assert win._resource_combo.currentText() == "GPIB0::15::INSTR"  # preserved
    assert win._refresh_btn.isEnabled()


def test_refresh_failure_reports_and_reenables(qtbot, monkeypatch) -> None:
    def _boom() -> list[str]:
        raise OSError("no VISA backend")

    monkeypatch.setattr("paramctl.ui.photoiv_workers.list_resources", _boom)
    win = PhotoIvWindow(_setup())
    qtbot.addWidget(win)

    win._on_refresh_resources()
    qtbot.waitUntil(lambda: win._disc_thread is None, timeout=5000)

    assert "VISA discovery failed" in win._status_bar.currentMessage()
    assert _combo_items(win) == ["Mock analyzer"]  # untouched on failure
    assert win._refresh_btn.isEnabled()


def test_discover_on_start_populates_without_a_click(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(
        "paramctl.ui.photoiv_workers.list_resources", lambda: ["GPIB0::15::INSTR"]
    )
    win = PhotoIvWindow(_setup(), discover_on_start=True)
    qtbot.addWidget(win)
    qtbot.waitUntil(
        lambda: "GPIB0::15::INSTR" in _combo_items(win), timeout=5000
    )
    assert win._resource_combo.currentText() == "Mock analyzer"  # selection kept
