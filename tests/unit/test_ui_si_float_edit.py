"""Tests for the SI-prefix-aware float-edit widget."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt

from paramctl.ui.widgets._si_float_edit import SiFloatEdit


def test_initial_value_is_rendered_with_unit(qtbot) -> None:
    edit = SiFloatEdit(1e-3, unit="A")
    qtbot.addWidget(edit)
    assert edit.text() == "1 mA"
    assert edit.value() == pytest.approx(1e-3)


def test_set_value_redraws(qtbot) -> None:
    edit = SiFloatEdit(0.0, unit="A")
    qtbot.addWidget(edit)
    edit.set_value(2.5e-6)
    assert edit.text() == "2.5 uA"
    assert edit.value() == pytest.approx(2.5e-6)


def test_set_unit_redraws_without_changing_value(qtbot) -> None:
    edit = SiFloatEdit(1.5e-3, unit="A")
    qtbot.addWidget(edit)
    assert edit.text() == "1.5 mA"
    edit.set_unit("V")
    assert edit.text() == "1.5 mV"
    assert edit.value() == pytest.approx(1.5e-3)


def test_typing_si_prefix_parses_on_edit_finished(qtbot) -> None:
    edit = SiFloatEdit(0.0, unit="A")
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)

    edit.clear()
    qtbot.keyClicks(edit, "100 u")
    qtbot.keyClick(edit, Qt.Key.Key_Return)

    assert edit.value() == pytest.approx(100e-6)
    assert edit.text() == "100 uA"


def test_typing_scientific_notation_still_works(qtbot) -> None:
    edit = SiFloatEdit(0.0, unit="A")
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)

    edit.clear()
    qtbot.keyClicks(edit, "1.5e-3")
    qtbot.keyClick(edit, Qt.Key.Key_Return)

    assert edit.value() == pytest.approx(1.5e-3)
    assert edit.text() == "1.5 mA"


def test_invalid_text_restores_previous_value(qtbot) -> None:
    edit = SiFloatEdit(1e-3, unit="A")
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)

    edit.clear()
    qtbot.keyClicks(edit, "garbage")
    qtbot.keyClick(edit, Qt.Key.Key_Return)

    assert edit.value() == pytest.approx(1e-3)
    assert edit.text() == "1 mA"


def test_value_changed_signal_fires_on_change(qtbot) -> None:
    edit = SiFloatEdit(0.0, unit="A")
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)

    received: list[float] = []
    edit.value_changed.connect(received.append)

    edit.clear()
    qtbot.keyClicks(edit, "5 m")
    qtbot.keyClick(edit, Qt.Key.Key_Return)

    assert received == [pytest.approx(5e-3)]


def test_value_changed_does_not_fire_on_no_op_edit(qtbot) -> None:
    edit = SiFloatEdit(1e-3, unit="A")
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)

    received: list[float] = []
    edit.value_changed.connect(received.append)

    # Type the same value (in different form) and commit.
    edit.clear()
    qtbot.keyClicks(edit, "0.001")
    qtbot.keyClick(edit, Qt.Key.Key_Return)

    assert received == []
