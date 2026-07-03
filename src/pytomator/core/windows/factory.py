"""Factory for the current platform's window controller."""

import sys
from typing import Optional

from pytomator.core.windows.window_controller import WindowController


def get_window_controller() -> Optional[WindowController]:
    """Return a supported controller, or None on unsupported platforms."""
    if sys.platform == "win32":
        from pytomator.core.windows.windows_window_controller import (
            WindowsWindowController,
        )

        return WindowsWindowController()
    return None
