"""Tests for live unit propagation between channel and sweep panels."""
from __future__ import annotations

from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepMeasurement,
    SweepRange,
)
from paramctl.ui.widgets import SetupEditor


def _smu1_var1_voltage() -> ChannelConfig:
    return ChannelConfig(
        channel_id=ChannelId.SMU1,
        mode=ChannelMode.V_SOURCE,
        function=ChannelFunction.VAR1,
        compliance=1e-3,
    )


def _smu1_var1_current() -> ChannelConfig:
    return ChannelConfig(
        channel_id=ChannelId.SMU1,
        mode=ChannelMode.I_SOURCE,
        function=ChannelFunction.VAR1,
        compliance=10.0,
    )


def test_voltage_var1_sets_sweep_unit_to_volts(qtbot) -> None:
    editor = SetupEditor()
    qtbot.addWidget(editor)

    setup = Setup(
        channels=[_smu1_var1_voltage()],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=2.0, points=11)
        ),
    )
    editor.populate_from(setup)

    assert editor._sweep._start.unit() == "V"
    assert editor._sweep._stop.unit() == "V"


def test_current_var1_sets_sweep_unit_to_amps(qtbot) -> None:
    editor = SetupEditor()
    qtbot.addWidget(editor)

    setup = Setup(
        channels=[_smu1_var1_current()],
        measurement=SweepMeasurement(
            var1=SweepRange(start=1e-6, stop=1e-3, points=21)
        ),
    )
    editor.populate_from(setup)

    assert editor._sweep._start.unit() == "A"
    assert editor._sweep._stop.unit() == "A"


def test_changing_var1_mode_updates_sweep_unit_live(qtbot) -> None:
    editor = SetupEditor()
    qtbot.addWidget(editor)

    setup = Setup(
        channels=[_smu1_var1_voltage()],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=2.0, points=11)
        ),
    )
    editor.populate_from(setup)
    assert editor._sweep._start.unit() == "V"

    smu1_row = editor._channels._rows[ChannelId.SMU1]
    smu1_row.mode_combo.setCurrentIndex(
        smu1_row.mode_combo.findData(ChannelMode.I_SOURCE)
    )

    assert editor._sweep._start.unit() == "A"
    assert editor._sweep._stop.unit() == "A"


def test_v_source_row_shows_v_for_source_and_a_for_compliance(qtbot) -> None:
    editor = SetupEditor()
    qtbot.addWidget(editor)
    smu1 = editor._channels._rows[ChannelId.SMU1]
    smu1.enable_check.setChecked(True)
    smu1.mode_combo.setCurrentIndex(smu1.mode_combo.findData(ChannelMode.V_SOURCE))

    assert smu1.source_edit.unit() == "V"
    assert smu1.compliance_edit.unit() == "A"


def test_i_source_row_swaps_source_and_compliance_units(qtbot) -> None:
    editor = SetupEditor()
    qtbot.addWidget(editor)
    smu1 = editor._channels._rows[ChannelId.SMU1]
    smu1.enable_check.setChecked(True)
    smu1.mode_combo.setCurrentIndex(smu1.mode_combo.findData(ChannelMode.I_SOURCE))

    assert smu1.source_edit.unit() == "A"
    assert smu1.compliance_edit.unit() == "V"


def test_no_var1_clears_sweep_unit(qtbot) -> None:
    editor = SetupEditor()
    qtbot.addWidget(editor)

    # Default editor state has all channels disabled -> no VAR1.
    assert editor._sweep._start.unit() == ""
