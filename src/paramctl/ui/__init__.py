"""PyQt6 user interface for paramctl.

The UI is the top of the layered architecture: it depends on engine,
models, and driver, but never the other way around. VISA calls live in
``SweepWorker`` (on a ``QThread``); the main thread does only Qt work.
"""
from __future__ import annotations

from .main_window import MainWindow
from .workers import SweepWorker

__all__ = ["MainWindow", "SweepWorker"]
