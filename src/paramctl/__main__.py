"""Entry point: ``python -m paramctl`` launches the GUI."""
from __future__ import annotations

import sys

from .ui.app import main

if __name__ == "__main__":
    sys.exit(main())
