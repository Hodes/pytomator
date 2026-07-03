"""Platform-independent contract for desktop window control."""

from abc import ABC, abstractmethod
from typing import Optional


WindowInfo = dict[str, int | str | None]


class WindowController(ABC):
    """Locate and focus top-level application windows."""

    @abstractmethod
    def find_window(self, title: str) -> Optional[WindowInfo]:
        """Find a visible window, preferring an exact title match."""

    @abstractmethod
    def focus_window(self, window: WindowInfo) -> bool:
        """Focus a window and confirm that it became foreground."""
