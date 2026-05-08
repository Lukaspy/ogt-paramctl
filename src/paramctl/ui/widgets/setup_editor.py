"""Combines the Channel and Sweep panels into one ``Setup`` editor.

The editor never holds a fully-validated ``Setup`` of its own. Instead,
:meth:`current_setup` is called on demand (e.g. when the user clicks Run);
that call constructs a ``Setup`` from the panel state, which then runs
through Pydantic validation. Validation errors propagate to the caller so
the UI can surface them in the status bar.
"""
from __future__ import annotations

import logging

from PyQt6.QtWidgets import QFormLayout, QGroupBox, QLineEdit, QVBoxLayout, QWidget

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


__all__ = ["SetupEditor"]
