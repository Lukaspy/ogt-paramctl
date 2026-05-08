"""Tests for the channel/sweep editor widgets."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    IntegrationTime,
    Setup,
    SweepDirection,
    SweepMeasurement,
    SweepRange,
    SweepScale,
)
from paramctl.ui.widgets import ChannelPanel, SetupEditor, SweepPanel


def _basic_setup() -> Setup:
    return Setup(
        name="ID-VDS @ VGS=1.5",
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10e-3,
                label="Drain",
            ),
            ChannelConfig(
                channel_id=ChannelId.SMU2,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.CONST,
                source_value=1.5,
                compliance=1e-3,
                label="Gate",
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=2.0, points=21)
        ),
    )


def test_channel_panel_round_trips_basic_setup(qtbot) -> None:
    panel = ChannelPanel()
    qtbot.addWidget(panel)
    setup = _basic_setup()

    panel.populate_from_setup(list(setup.channels))
    out = panel.current_channels()

    assert {c.channel_id for c in out} == {ChannelId.SMU1, ChannelId.SMU2}
    smu1 = next(c for c in out if c.channel_id is ChannelId.SMU1)
    assert smu1.function is ChannelFunction.VAR1
    assert smu1.compliance == pytest.approx(10e-3)
    assert smu1.label == "Drain"

    smu2 = next(c for c in out if c.channel_id is ChannelId.SMU2)
    assert smu2.source_value == pytest.approx(1.5)
    assert smu2.label == "Gate"


def test_channel_panel_disabled_channels_omitted(qtbot) -> None:
    panel = ChannelPanel()
    qtbot.addWidget(panel)
    panel.populate_from_setup([
        ChannelConfig(
            channel_id=ChannelId.SMU1,
            mode=ChannelMode.V_SOURCE,
            function=ChannelFunction.VAR1,
            compliance=1e-3,
        ),
    ])

    assert {c.channel_id for c in panel.current_channels()} == {ChannelId.SMU1}


def test_channel_panel_compliance_disabled_for_non_source_mode(qtbot) -> None:
    panel = ChannelPanel()
    qtbot.addWidget(panel)
    # Find SMU3's row, set its mode to COMMON, and verify compliance is
    # disabled in the UI (not a validation error — a UI affordance).
    row = panel._rows[ChannelId.SMU3]
    row.enable_check.setChecked(True)
    row.mode_combo.setCurrentIndex(row.mode_combo.findData(ChannelMode.COMMON))
    assert not row.compliance_edit.isEnabled()
    assert not row.source_edit.isEnabled()


def test_sweep_panel_round_trips(qtbot) -> None:
    panel = SweepPanel()
    qtbot.addWidget(panel)
    measurement = SweepMeasurement(
        var1=SweepRange(
            start=1e-3,
            stop=1.0,
            points=51,
            scale=SweepScale.LOG10,
            direction=SweepDirection.DOUBLE,
        ),
        integration=IntegrationTime.LONG,
        hold_time=0.05,
        delay_time=0.01,
    )
    panel.populate_from(measurement)
    out = panel.current_measurement()

    assert out.var1.start == pytest.approx(1e-3)
    assert out.var1.stop == pytest.approx(1.0)
    assert out.var1.points == 51
    assert out.var1.scale is SweepScale.LOG10
    assert out.var1.direction is SweepDirection.DOUBLE
    assert out.integration is IntegrationTime.LONG
    assert out.hold_time == pytest.approx(0.05)
    assert out.delay_time == pytest.approx(0.01)


def test_setup_editor_round_trips(qtbot) -> None:
    editor = SetupEditor()
    qtbot.addWidget(editor)
    setup = _basic_setup()

    editor.populate_from(setup)
    out = editor.current_setup()

    assert out.name == setup.name
    assert {c.channel_id for c in out.channels} == {ChannelId.SMU1, ChannelId.SMU2}
    assert isinstance(out.measurement, SweepMeasurement)
    assert out.measurement.var1.points == 21


def test_setup_editor_raises_validation_error_on_invalid_state(qtbot) -> None:
    """A setup with no VAR1 channel must surface as a Pydantic ValidationError.

    The MainWindow catches that and shows a message; here we just verify the
    editor does not silently produce a bad setup. We poke the widgets
    directly because the corresponding Setup is itself unconstructible — the
    very condition we want the UI to detect.
    """
    editor = SetupEditor()
    qtbot.addWidget(editor)

    smu1_row = editor._channels._rows[ChannelId.SMU1]
    smu1_row.enable_check.setChecked(True)
    smu1_row.mode_combo.setCurrentIndex(
        smu1_row.mode_combo.findData(ChannelMode.V_SOURCE)
    )
    smu1_row.function_combo.setCurrentIndex(
        smu1_row.function_combo.findData(ChannelFunction.CONST)
    )
    smu1_row.compliance_edit.set_value(1e-3)

    with pytest.raises(ValidationError):
        editor.current_setup()
