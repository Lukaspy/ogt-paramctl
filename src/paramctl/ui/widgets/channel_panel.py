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
from ._float_edit import FloatEdit

logger = logging.getLogger(__name__)

_M0_CHANNELS: tuple[ChannelId, ...] = (
    ChannelId.SMU1,
    ChannelId.SMU2,
    ChannelId.SMU3,
    ChannelId.SMU4,
)

_DEFAULT_COMPLIANCE_BY_MODE: dict[ChannelMode, float] = {
    ChannelMode.V_SOURCE: 1e-3,   # 1 mA when sourcing voltage
    ChannelMode.I_SOURCE: 10.0,   # 10 V when sourcing current
}


class ChannelRow:
    """Widgets for a single channel's row plus the to/from ``ChannelConfig`` glue.

    Not a ``QWidget`` itself — it owns several widgets that the panel adds to
    its grid layout. The panel calls :meth:`build_config` per row when
    assembling the active ``Setup``.
    """

    changed = pyqtSignal()

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

        self.source_edit = FloatEdit(0.0, parent)
        self.compliance_edit = FloatEdit(1e-3, parent)
        self.label_edit = QLineEdit(parent)
        self.label_edit.setPlaceholderText("optional label")

        self.mode_combo.currentIndexChanged.connect(self._sync_enabled_state)

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

    def _sync_enabled_state(self) -> None:
        is_source = self.mode in (ChannelMode.V_SOURCE, ChannelMode.I_SOURCE)
        self.source_edit.setEnabled(is_source)
        self.compliance_edit.setEnabled(is_source)

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
        """Push values from a ``ChannelConfig`` into the widgets."""
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
        self._sync_enabled_state()


class ChannelPanel(QGroupBox):
    """Editor for the per-channel section of a ``Setup``."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Channels", parent)
        self._rows: dict[ChannelId, ChannelRow] = {}
        self._build_ui()

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

    # -- public API ----------------------------------------------------------

    def populate_from_setup(self, channels: list[ChannelConfig]) -> None:
        by_id: dict[ChannelId, ChannelConfig] = {c.channel_id: c for c in channels}
        for ch_id, row in self._rows.items():
            row.populate_from(by_id.get(ch_id))

    def current_channels(self) -> list[ChannelConfig]:
        out: list[ChannelConfig] = []
        for row in self._rows.values():
            cfg = row.build_config()
            if cfg is not None:
                out.append(cfg)
        return out


__all__ = ["ChannelPanel", "ChannelRow"]
