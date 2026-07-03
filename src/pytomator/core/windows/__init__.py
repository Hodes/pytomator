"""Cross-platform desktop window control."""

from pytomator.core.windows.factory import get_window_controller
from pytomator.core.windows.window_controller import WindowController, WindowInfo

__all__ = ["WindowController", "WindowInfo", "get_window_controller"]
