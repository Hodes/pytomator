"""Screen capture utilities using MSS and win32gui for window info.

Supports multi-monitor setups by using the virtual screen (all monitors combined).
"""

import sys
from pathlib import Path
from typing import Optional

import mss
import mss.tools
from PIL import Image

from pytomator.core.vision.models import TemplateCapture


def _get_virtual_monitor() -> dict:
    """Return the virtual monitor dict that encompasses all monitors.

    MSS monitor[0] is the virtual screen combining all monitors.
    On single-monitor setups, this is the same as monitor[1].
    """
    with mss.mss() as sct:
        return sct.monitors[0]


def capture_region(x: int, y: int, w: int, h: int) -> Image.Image:
    """Capture a specific screen region and return a PIL Image.

    Works across all monitors in a multi-monitor setup.

    Args:
        x: Left coordinate (may be negative if on a left-side monitor).
        y: Top coordinate (may be negative if on a top-side monitor).
        w: Width of the region.
        h: Height of the region.

    Returns:
        PIL Image of the captured region.
    """
    with mss.mss() as sct:
        monitor = {"left": x, "top": y, "width": w, "height": h}
        sct_img = sct.grab(monitor)
        return Image.frombytes("RGB", sct_img.size, sct_img.rgb)


def capture_full_screen() -> Image.Image:
    """Capture the entire virtual screen (all monitors) and return a PIL Image."""
    with mss.mss() as sct:
        monitor = sct.monitors[0]  # Virtual screen (all monitors)
        sct_img = sct.grab(monitor)
        return Image.frombytes("RGB", sct_img.size, sct_img.rgb)


def get_screen_size() -> tuple[int, int, int, int]:
    """Return (left, top, width, height) of the virtual screen (all monitors).

    On multi-monitor setups, left/top may be negative if a monitor is
    positioned to the left or above the primary monitor.

    Returns:
        Tuple (left, top, width, height) of the virtual screen.
    """
    monitor = _get_virtual_monitor()
    return monitor["left"], monitor["top"], monitor["width"], monitor["height"]


def get_physical_monitors() -> list[dict]:
    """Return a list of physical monitor dicts from MSS.

    MSS monitor[0] is the virtual screen; monitors[1:] are physical monitors.
    Each dict has keys: 'left', 'top', 'width', 'height'.

    Returns:
        List of monitor dicts, one per physical monitor.
    """
    with mss.mss() as sct:
        return sct.monitors[1:]  # Skip index 0 (virtual screen)


def get_active_window_info() -> dict:
    """Get information about the currently active window.

    Returns:
        dict with keys: 'title', 'left', 'top', 'width', 'height'
        On non-Windows platforms, returns empty data.
    """
    result = {
        "id": None,
        "title": None,
        "left": 0,
        "top": 0,
        "width": 0,
        "height": 0,
    }

    if sys.platform == "win32":
        try:
            import win32gui  # type: ignore
            import win32con  # type: ignore

            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                result["id"] = hwnd
                result["title"] = win32gui.GetWindowText(hwnd)
                # Get window rect (including title bar and borders)
                rect = win32gui.GetWindowRect(hwnd)
                result["left"] = rect[0]
                result["top"] = rect[1]
                result["width"] = rect[2] - rect[0]
                result["height"] = rect[3] - rect[1]
        except ImportError:
            pass  # pywin32 not installed
        except Exception:
            pass  # Silently fail on any win32 error

    return result


def get_monitor_at_point(x: int, y: int) -> dict:
    """Return the physical monitor containing a point, or the nearest monitor."""
    monitors = get_physical_monitors()
    for monitor in monitors:
        if (
            monitor["left"] <= x < monitor["left"] + monitor["width"]
            and monitor["top"] <= y < monitor["top"] + monitor["height"]
        ):
            return monitor

    if not monitors:
        left, top, width, height = get_screen_size()
        return {"left": left, "top": top, "width": width, "height": height}

    return min(
        monitors,
        key=lambda monitor: (
            x - (monitor["left"] + monitor["width"] // 2)
        ) ** 2
        + (
            y - (monitor["top"] + monitor["height"] // 2)
        ) ** 2,
    )


def get_active_search_region(
    window_info: Optional[dict] = None,
) -> tuple[dict, dict]:
    """Return the visible active-window region and its focus snapshot."""
    window = window_info or get_active_window_info()
    v_left, v_top, v_width, v_height = get_screen_size()
    v_right = v_left + v_width
    v_bottom = v_top + v_height

    if window["width"] > 0 and window["height"] > 0:
        left = max(window["left"], v_left)
        top = max(window["top"], v_top)
        right = min(window["left"] + window["width"], v_right)
        bottom = min(window["top"] + window["height"], v_bottom)
        if right > left and bottom > top:
            return (
                {"left": left, "top": top, "width": right - left, "height": bottom - top},
                window,
            )
        point_x = window["left"] + window["width"] // 2
        point_y = window["top"] + window["height"] // 2
    else:
        import pyautogui

        cursor = pyautogui.position()
        point_x, point_y = cursor.x, cursor.y

    return get_monitor_at_point(point_x, point_y), window


def _get_project_dir(project_path: Path) -> Path:
    """Return the project directory, handling both .pytom files and directories."""
    if project_path.suffix == ".pytom":
        return project_path.parent
    return project_path


def save_template_image(
    project_path: Path,
    template_id: str,
    image: Image.Image,
) -> str:
    """Save a template image to the project's templates directory.

    Args:
        project_path: Path to the .pytom file or project directory.
        template_id: Unique ID for the template (used as filename).
        image: PIL Image to save.

    Returns:
        Relative path string (e.g. 'templates/<id>.png').
    """
    project_dir = _get_project_dir(project_path)
    templates_dir = project_dir / "templates"
    templates_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{template_id}.png"
    filepath = templates_dir / filename
    image.save(filepath, "PNG")

    return f"templates/{filename}"


def load_template_image(project_path: Path, image_path: str) -> Optional[Image.Image]:
    """Load a template image from the project's templates directory.

    Args:
        project_path: Path to the .pytom file or project directory.
        image_path: Relative path (e.g. 'templates/<id>.png').

    Returns:
        PIL Image or None if not found.
    """
    project_dir = _get_project_dir(project_path)
    full_path = project_dir / image_path
    if not full_path.exists():
        return None
    return Image.open(full_path)
