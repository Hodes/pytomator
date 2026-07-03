"""Prepare a stable window region for template matching."""

from dataclasses import dataclass
from typing import Optional

from pytomator.core.vision import capture_tool
from pytomator.core.vision.models import TemplateCapture
from pytomator.core.windows import WindowInfo, get_window_controller


@dataclass(frozen=True)
class SearchContext:
    region: dict
    window: WindowInfo


def prepare_search_context(
    template: TemplateCapture,
    *,
    autofocus: bool = False,
) -> Optional[SearchContext]:
    """Optionally focus the template's window and return its search region."""
    window: Optional[WindowInfo] = None
    if autofocus:
        if not template.active_window_title:
            return None
        controller = get_window_controller()
        if controller is None:
            return None
        window = controller.find_window(template.active_window_title)
        if window is None or not controller.focus_window(window):
            return None
        focused_window = capture_tool.get_active_window_info()
        if focused_window.get("id") != window.get("id"):
            return None
        window = focused_window

    region, snapshot = capture_tool.get_active_search_region(window)
    return SearchContext(region=region, window=snapshot)
