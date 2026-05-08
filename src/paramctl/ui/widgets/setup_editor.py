"""Combines the Channel and Sweep panels into one ``Setup`` editor.

Coordinates the two panels:
  - constructs a validated ``Setup`` on demand (``current_setup()``);
  - propagates VAR1 unit changes from the channel panel into the sweep
    panel so start/stop fields show V when VAR1 is V-sourcing and A when
    VAR1 is I-sourcing.
"""
from __future__ import annotations

import logging

from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLineEdit, QVBoxLayout, QWidget

from ...models.channel import ChannelMode
from ...models.setup import Setup
from .channel_panel import ChannelPanel
from .sweep_panel import SweepPanel

logger = logging.getLogger(__name__)


class SetupEditor(QWidget):
    """Channel + sweep editor with a setup-name field on top."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._name_edit = QLineEdit(self)
        self._name_edit.setPlaceholderText("untitled setup")

        meta_box = QGroupBox("Setup", self)
        meta_form = QFormLayout(meta_box)
        meta_form.addRow("Name", self._name_edit)

        self._channels = ChannelPanel(self)
        self._sweep = SweepPanel(self)

        layout = QVBoxLayout(self)
        layout.addWidget(meta_box)
        layout.addWidget(self._channels)
        layout.addWidget(self._sweep)
        layout.addStretch(1)

        self._channels.channels_changed.connect(self._sync_var1_unit)
        self._sync_var1_unit()

    def populate_from(self, setup: Setup) -> None:
        self._name_edit.setText(setup.name)
        self._channels.populate_from_setup(list(setup.channels))
        if hasattr(setup.measurement, "var1"):
            self._sweep.populate_from(setup.measurement)  # type: ignore[arg-type]

    def current_setup(self) -> Setup:
        """Build a validated ``Setup`` from the current widget state.

        Raises ``pydantic.ValidationError`` when the panel state does not
        produce a self-consistent ``Setup`` (e.g. zero VAR1 channels, sweep
        ``start == stop``, etc.). Callers should catch and surface to the UI.
        """
        return Setup(
            name=self._name_edit.text(),
            channels=self._channels.current_channels(),
            measurement=self._sweep.current_measurement(),
        )

    def _sync_var1_unit(self) -> None:
        """Push the VAR1 channel's unit into the sweep panel's start/stop fields."""
        var1 = self._channels.find_var1_row()
        if var1 is None:
            self._sweep.set_var1_unit("")
            return
        unit = "V" if var1.mode is ChannelMode.V_SOURCE else "A"
        self._sweep.set_var1_unit(unit)


__all__ = ["SetupEditor"]
