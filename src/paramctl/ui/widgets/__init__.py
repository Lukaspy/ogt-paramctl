"""UI widgets for paramctl. Each widget is dumb — it renders a model state
or accepts an event, never makes a VISA call directly.
"""
from __future__ import annotations

from .plot_view import PlotView

__all__ = ["PlotView"]
