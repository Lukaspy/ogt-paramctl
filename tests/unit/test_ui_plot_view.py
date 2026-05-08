"""Direct tests for ``PlotView`` axis labelling, log-Y toggle, and cursor wiring."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from paramctl.models import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
    Setup,
    SweepMeasurement,
    SweepRange,
)
from paramctl.ui.widgets import PlotView


def _v_source_setup() -> Setup:
    return Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.V_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=1e-3,
                label="Drain",
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=0.0, stop=1.0, points=11)
        ),
    )


def _i_source_setup() -> Setup:
    return Setup(
        channels=[
            ChannelConfig(
                channel_id=ChannelId.SMU1,
                mode=ChannelMode.I_SOURCE,
                function=ChannelFunction.VAR1,
                compliance=10.0,
                label="Anode",
            ),
        ],
        measurement=SweepMeasurement(
            var1=SweepRange(start=1e-6, stop=1e-3, points=21)
        ),
    )


def test_v_source_setup_sets_axis_units(qtbot) -> None:
    view = PlotView()
    qtbot.addWidget(view)
    view.begin_run(_v_source_setup())
    assert view.x_unit == "V"
    assert view.y_unit == "A"


def test_i_source_setup_swaps_axis_units(qtbot) -> None:
    view = PlotView()
    qtbot.addWidget(view)
    view.begin_run(_i_source_setup())
    assert view.x_unit == "A"
    assert view.y_unit == "V"


def test_axis_label_uses_channel_label(qtbot) -> None:
    view = PlotView()
    qtbot.addWidget(view)
    view.begin_run(_v_source_setup())
    bottom = view._plot.getAxis("bottom").labelText
    left = view._plot.getAxis("left").labelText
    assert "Drain" in bottom
    assert "voltage" in bottom
    assert "Drain" in left
    assert "current" in left


def test_set_log_y_round_trips(qtbot) -> None:
    view = PlotView()
    qtbot.addWidget(view)
    assert view.is_log_y() is False
    view.set_log_y(True)
    assert view.is_log_y() is True
    view.set_log_y(False)
    assert view.is_log_y() is False


def test_cursor_changed_emits_pre_formatted_string(qtbot) -> None:
    view = PlotView()
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()
    qtbot.waitExposed(view)
    view.begin_run(_v_source_setup())

    received: list[str] = []
    view.cursor_changed.connect(received.append)

    # Map a known view-coordinate (0.5 V, 1e-3 A) back to a scene position
    # and feed it directly to the slot.
    item = view._plot.plotItem
    scene_pos = item.vb.mapViewToScene(QPointF(0.5, 1e-3))
    view._on_mouse_moved(scene_pos)

    assert received, "cursor_changed should fire on mouse-over"
    text = received[-1]
    # Format is "X: <value><opt-prefix>V    Y: <value><opt-prefix>A".
    # Check for V-suffix (X) and A-suffix (Y) at unit positions.
    import re
    assert re.search(r"X:[^A]*V", text), f"no V unit in X part: {text!r}"
    assert re.search(r"Y:.*A", text), f"no A unit in Y part: {text!r}"


def test_cursor_emits_empty_string_when_outside_plot(qtbot) -> None:
    view = PlotView()
    qtbot.addWidget(view)
    view.resize(400, 300)
    view.show()
    qtbot.waitExposed(view)
    view.begin_run(_v_source_setup())

    received: list[str] = []
    view.cursor_changed.connect(received.append)

    # Definitely outside the plot's scene rect.
    view._on_mouse_moved(QPointF(-1000.0, -1000.0))

    assert received[-1] == ""


def test_log_y_toggle_takes_effect_before_a_run(qtbot) -> None:
    """Toggling log Y before any run is harmless and persists."""
    view = PlotView()
    qtbot.addWidget(view)
    view.set_log_y(True)
    view.begin_run(_v_source_setup())
    assert view.is_log_y() is True


@pytest.mark.parametrize("v_source", [True, False])
def test_axis_units_match_var1_mode(qtbot, v_source: bool) -> None:
    view = PlotView()
    qtbot.addWidget(view)
    setup = _v_source_setup() if v_source else _i_source_setup()
    view.begin_run(setup)
    if v_source:
        assert view.x_unit == "V" and view.y_unit == "A"
    else:
        assert view.x_unit == "A" and view.y_unit == "V"
