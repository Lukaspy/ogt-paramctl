"""UI widgets for paramctl. Each widget is dumb — it renders a model state
or accepts an event, never makes a VISA call directly.
"""
from __future__ import annotations

from .channel_panel import ChannelPanel
from .plot_view import PlotView
from .setup_editor import SetupEditor
from .sweep_panel import SweepPanel

__all__ = ["ChannelPanel", "PlotView", "SetupEditor", "SweepPanel"]
