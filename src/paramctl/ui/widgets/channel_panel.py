"""Per-channel editor: one row per SMU with mode / function / source / compliance.

VSU/VMU/GNDU rows are out of scope for the M0 UI — the FlexDriver does not
yet support those channels. When it does, extend ``_M0_CHANNELS`` and the
mode-allowed rules in ``ChannelRow``.
"""
from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ...models.channel import (
    ChannelConfig,
    ChannelFunction,
    ChannelId,
    ChannelMode,
)
from ._si_float_edit import SiFloatEdit

logger = logging.getLogger(__name__)

_M0_CHANNELS: tuple[ChannelId, ...] = (
    ChannelId.SMU1,
    ChannelId.SMU2,
    ChannelId.SMU3,
    ChannelId.SMU4,
)


def _units_for_mode(mode: ChannelMode) -> tuple[str, str]:
    """Return ``(source_unit, compliance_unit)`` for a channel mode.

    V_SOURCE: source is volts, compliance is current (amps).
    I_SOURCE: source is amps, compliance is voltage (volts).
    Other modes: both fields are disabled, so their units do not matter —
    return empty strings to avoid stale labels.
    """
    if mode is ChannelMode.V_SOURCE:
        return "V", "A"
    if mode is ChannelMode.I_SOURCE:
        return "A", "V"
    return "", ""


class ChannelRow:
    """Widgets for a single channel's row plus the to/from ``ChannelConfig`` glue."""

    def __init__(self, channel_id: ChannelId, parent: QWidget) -> None:
        self.channel_id = channel_id
        self.enable_check = QCheckBox(parent)
        self.id_label = QLabel(channel_id.value, parent)

        self.mode_combo = QComboBox(parent)
        for mode in ChannelMode:
            self.mode_combo.addItem(mode.value, mode)

        self.function_combo = QComboBox(parent)
        for fn in ChannelFunction:
            self.function_combo.addItem(fn.value, fn)

        self.source_edit = SiFloatEdit(0.0, unit="V", parent=parent)
        self.compliance_edit = SiFloatEdit(1e-3, unit="A", parent=parent)
        self.label_edit = QLineEdit(parent)
        self.label_edit.setPlaceholderText("optional label")

        self.mode_combo.currentIndexChanged.connect(self._sync_unit_state)
        self._sync_unit_state()

    @property
    def enabled(self) -> bool:
        return self.enable_check.isChecked()

    @property
    def mode(self) -> ChannelMode:
        data = self.mode_combo.currentData()
        assert isinstance(data, ChannelMode)
        return data

    @property
    def function(self) -> ChannelFunction:
        data = self.function_combo.currentData()
        assert isinstance(data, ChannelFunction)
        return data

    def _sync_unit_state(self) -> None:
        is_source = self.mode in (ChannelMode.V_SOURCE, ChannelMode.I_SOURCE)
        self.source_edit.setEnabled(is_source)
        self.compliance_edit.setEnabled(is_source)
        source_unit, compliance_unit = _units_for_mode(self.mode)
        self.source_edit.set_unit(source_unit)
        self.compliance_edit.set_unit(compliance_unit)

    def build_config(self) -> ChannelConfig | None:
        """Translate the row state to a ``ChannelConfig``, or ``None`` if disabled."""
        if not self.enabled:
            return None
        mode = self.mode
        function = self.function
        compliance: float | None = None
        if mode in (ChannelMode.V_SOURCE, ChannelMode.I_SOURCE):
            compliance = self.compliance_edit.value()
        return ChannelConfig(
            channel_id=self.channel_id,
            mode=mode,
            function=function,
            source_value=self.source_edit.value(),
            compliance=compliance,
            label=self.label_edit.text(),
        )

    def populate_from(self, config: ChannelConfig | None) -> None:
        if config is None:
            self.enable_check.setChecked(False)
            self.mode_combo.setCurrentIndex(
                self.mode_combo.findData(ChannelMode.DISABLED)
            )
            self.function_combo.setCurrentIndex(
                self.function_combo.findData(ChannelFunction.CONST)
            )
            self.source_edit.set_value(0.0)
            self.compliance_edit.set_value(1e-3)
            self.label_edit.setText("")
        else:
            self.enable_check.setChecked(True)
            self.mode_combo.setCurrentIndex(self.mode_combo.findData(config.mode))
            self.function_combo.setCurrentIndex(
                self.function_combo.findData(config.function)
            )
            self.source_edit.set_value(config.source_value)
            if config.compliance is not None:
                self.compliance_edit.set_value(config.compliance)
            self.label_edit.setText(config.label)
        self._sync_unit_state()


class ChannelPanel(QGroupBox):
    """Editor for the per-channel section of a ``Setup``.

    Emits ``channels_changed`` whenever the *structural* state of any row
    changes (enable / mode / function). Numeric edits do not fire it
    because they do not affect downstream unit labels — only the structural
    bits do.
    """

    channels_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Channels", parent)
        self._rows: dict[ChannelId, ChannelRow] = {}
        self._build_ui()
        self._wire_change_signals()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        outer.addLayout(grid)

        headers = [
            "On",
            "Channel",
            "Mode",
            "Function",
            "Source value",
            "Compliance",
            "Label",
        ]
        for col, label in enumerate(headers):
            header = QLabel(label)
            header.setAlignment(Qt.AlignmentFlag.AlignLeft)
            grid.addWidget(header, 0, col)

        for row_index, channel_id in enumerate(_M0_CHANNELS, start=1):
            row = ChannelRow(channel_id, self)
            grid.addWidget(row.enable_check, row_index, 0)
            grid.addWidget(row.id_label, row_index, 1)
            grid.addWidget(row.mode_combo, row_index, 2)
            grid.addWidget(row.function_combo, row_index, 3)
            grid.addWidget(row.source_edit, row_index, 4)
            grid.addWidget(row.compliance_edit, row_index, 5)
            grid.addWidget(row.label_edit, row_index, 6)
            self._rows[channel_id] = row

    def _wire_change_signals(self) -> None:
        for row in self._rows.values():
            row.enable_check.stateChanged.connect(self.channels_changed)
            row.mode_combo.currentIndexChanged.connect(self.channels_changed)
            row.function_combo.currentIndexChanged.connect(self.channels_changed)

    # -- public API ----------------------------------------------------------

    def populate_from_setup(self, channels: list[ChannelConfig]) -> None:
        by_id: dict[ChannelId, ChannelConfig] = {c.channel_id: c for c in channels}
        for ch_id, row in self._rows.items():
            row.populate_from(by_id.get(ch_id))
        self.channels_changed.emit()

    def current_channels(self) -> list[ChannelConfig]:
        out: list[ChannelConfig] = []
        for row in self._rows.values():
            cfg = row.build_config()
            if cfg is not None:
                out.append(cfg)
        return out

    def find_var1_row(self) -> ChannelRow | None:
        """The row currently configured as VAR1, if any (and enabled)."""
        for row in self._rows.values():
            if row.enabled and row.function is ChannelFunction.VAR1:
                return row
        return None


__all__ = ["ChannelPanel", "ChannelRow"]
