import sys
import time
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import pyautogui
from pytomator.core.decorators import pytomator_api
from pytomator.core.global_interruption_controller import should_stop
from pytomator.core.script_interrupted import ScriptInterrupted

if TYPE_CHECKING:
    from pytomator.project.manager import ProjectManager

ENTER = "enter"
ESC = "esc"

use_direct_input_keys = sys.platform == "win32"
if use_direct_input_keys:
    import pydirectinput

# ── Registry for ProjectManager (set by MainWindow) ──
_project_manager: "ProjectManager | None" = None
_import_cache: dict[str, "_ScriptNamespace"] = {}


class _ScriptNamespace:
    """Wrapper around a script's execution namespace for import_script()."""

    def __init__(self, ns: dict):
        self._ns = ns

    def __getattr__(self, name: str):
        try:
            return self._ns[name]
        except KeyError:
            raise AttributeError(f"Script has no attribute '{name}'")


def set_project_manager(pm: "ProjectManager | None") -> None:
    """Set the active ProjectManager instance (called by MainWindow at runtime)."""
    global _project_manager
    _project_manager = pm


def reset_import_cache() -> None:
    """Clear the import cache. Called before each script run cycle."""
    global _import_cache
    _import_cache = {}
    from pytomator.core.vision.template_matcher import reset_scale_cache

    reset_scale_cache()


# ═══════════════════════════════════════════════════════════════
# Vision / Template Matching API
# ═══════════════════════════════════════════════════════════════

def _get_template(name: str):
    """Helper: find a TemplateCapture by name in the current project."""
    if _project_manager is None or not _project_manager.is_project_open:
        raise NameError("No project is currently open — cannot access templates")
    project = _project_manager.project
    if project is None:
        raise NameError("No project is currently open")
    for t in project.templates:
        if t.name == name:
            return t
    raise NameError(f"Template '{name}' not found in the current project")


def _get_project_path() -> Path:
    """Helper: get the project path."""
    if _project_manager is None or not _project_manager.is_project_open:
        raise NameError("No project is currently open")
    path = _project_manager.project_path
    if path is None:
        raise NameError("Project path is not set (unsaved project?)")
    return path


def _vision_debug_enabled() -> bool:
    project = _project_manager.project if _project_manager is not None else None
    return bool(project and project.settings.vision_debug)


def _validate_backend(backend: str) -> str:
    backend = backend.lower()
    if backend not in {"standard", "directinput"}:
        raise ValueError("backend must be 'standard' or 'directinput'")
    if backend == "directinput" and sys.platform != "win32":
        raise RuntimeError("The directinput mouse backend is available only on Windows")
    return backend


def _resolve_mouse_backend(backend: Optional[str] = None) -> str:
    """Resolve an explicit backend or inherit the current project default."""
    if backend is not None:
        return _validate_backend(backend)

    project = _project_manager.project if _project_manager is not None else None
    configured = project.settings.mouse_backend if project is not None else "standard"
    configured = configured.lower()
    if configured not in {"standard", "directinput"}:
        return "standard"
    if configured == "directinput" and sys.platform != "win32":
        return "standard"
    return configured


def _mouse_for_backend(backend: Optional[str] = None):
    resolved = _resolve_mouse_backend(backend)
    return (pydirectinput if resolved == "directinput" else pyautogui), resolved


def _backend_button(button: str, backend: str) -> str:
    if backend == "directinput":
        return {"primary": "left", "secondary": "right"}.get(button, button)
    return button


def _resolve_mouse_movement(
    duration: Optional[float] = None,
    easing: Optional[str] = None,
) -> tuple[float, str]:
    project = _project_manager.project if _project_manager is not None else None
    settings = project.settings if project is not None else None
    resolved_duration = (
        duration
        if duration is not None
        else getattr(settings, "mouse_move_duration", 0.3)
    )
    resolved_easing = (
        easing
        if easing is not None
        else getattr(settings, "mouse_move_easing", "ease_out")
    )
    if resolved_duration < 0:
        raise ValueError("duration must be non-negative")
    if resolved_easing not in {"linear", "ease_out", "ease_in_out"}:
        raise ValueError("easing must be 'linear', 'ease_out', or 'ease_in_out'")
    return float(resolved_duration), resolved_easing


def _ease(progress: float, easing: str) -> float:
    if easing == "linear":
        return progress
    if easing == "ease_out":
        return 1 - (1 - progress) ** 3
    if easing == "ease_in_out":
        return (
            4 * progress ** 3
            if progress < 0.5
            else 1 - ((-2 * progress + 2) ** 3) / 2
        )
    raise ValueError("easing must be 'linear', 'ease_out', or 'ease_in_out'")


def _interpolate_mouse_positions(
    start: tuple[int, int],
    destination: tuple[int, int],
    duration: float,
    easing: str,
) -> list[tuple[int, int]]:
    if duration < 0:
        raise ValueError("duration must be non-negative")
    if easing not in {"linear", "ease_out", "ease_in_out"}:
        raise ValueError("easing must be 'linear', 'ease_out', or 'ease_in_out'")
    if duration == 0 or start == destination:
        return [destination]

    steps = max(2, ceil(duration / 0.0125))
    sx, sy = start
    dx, dy = destination[0] - sx, destination[1] - sy
    positions = []
    for step in range(1, steps + 1):
        progress = _ease(step / steps, easing)
        positions.append((
            round(sx + dx * progress),
            round(sy + dy * progress),
        ))
    positions[-1] = destination
    return positions


def _move_mouse_to(
    destination: tuple[int, int],
    backend: Optional[str] = None,
    duration: Optional[float] = None,
    easing: Optional[str] = None,
) -> None:
    mouse, resolved_backend = _mouse_for_backend(backend)
    duration, easing = _resolve_mouse_movement(duration, easing)
    start = tuple(mouse.position())
    positions = _interpolate_mouse_positions(start, destination, duration, easing)

    if len(positions) == 1:
        mouse.moveTo(*destination)
        return

    interval = duration / len(positions)
    emitted = start
    for index, position in enumerate(positions):
        if should_stop():
            raise ScriptInterrupted()
        if resolved_backend == "directinput":
            delta_x = position[0] - emitted[0]
            delta_y = position[1] - emitted[1]
            mouse.moveRel(delta_x, delta_y, relative=True)
        else:
            mouse.moveTo(*position)
        emitted = position
        if index < len(positions) - 1:
            time.sleep(interval)
    if resolved_backend == "directinput" and tuple(mouse.position()) != destination:
        mouse.moveTo(*destination)


def _find_template_with_context(name, confidence=None, autofocus=None):
    from pytomator.core.vision.template_matcher import find_on_screen
    from pytomator.core.vision.search_context import prepare_search_context

    template = _get_template(name)
    context = prepare_search_context(template, autofocus=autofocus)
    if context is None:
        return None, None
    region = find_on_screen(
        template,
        _get_project_path(),
        confidence,
        search_region=context.region,
        debug=_vision_debug_enabled(),
        window_info=context.window,
    )
    return region, context


def _window_still_active(context) -> bool:
    from pytomator.core.vision.capture_tool import get_active_window_info

    window_id = context.window.get("id")
    return window_id is None or get_active_window_info().get("id") == window_id


def _sleep_interruptibly(seconds: float) -> None:
    if seconds < 0:
        raise ValueError("interval must be non-negative")
    end = time.monotonic() + seconds
    while True:
        if should_stop():
            raise ScriptInterrupted()
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.05, remaining))


def _mouse_drag(start, destination, duration: float, backend: Optional[str]) -> None:
    if duration < 0:
        raise ValueError("duration must be non-negative")
    mouse, backend = _mouse_for_backend(backend)
    mouse.moveTo(*start)
    mouse.mouseDown(button=_backend_button("primary", backend))
    try:
        mouse.moveTo(*destination, duration=duration)
    finally:
        mouse.mouseUp(button=_backend_button("primary", backend))


@pytomator_api(
    description="Finds a template on the screen by name and returns its bounding box (x, y, w, h). "
                "Returns None if the template is not found.",
    params={
        "name": "Name of the template (must exist in the current project).",
        "confidence": "Confidence threshold (0.0 to 1.0). If omitted, uses the template's default confidence.",
        "autofocus": "If True, focuses the window associated with the template before searching.",
    },
    category="Vision",
    returns="Tuple (x, y, w, h) or None.",
    examples=[
        "region = find_template('btn_login')",
        "if region: click('primary', region[0] + region[2] // 2, region[1] + region[3] // 2)",
        "region = find_template('icon_settings', confidence=0.9)",
        "region = find_template('btn_login', autofocus=True)",
    ],
    version="1.0",
)
def find_template(
    name: str,
    confidence: Optional[float] = None,
    autofocus: Optional[bool] = None,
):
    """Find a template on the screen and return its bounding box."""
    return _find_template_with_context(name, confidence, autofocus)[0]


def _resolve_position(
    region: tuple[int, int, int, int],
    position: str | tuple[int, int],
) -> tuple[int, int]:
    """Resolve a position string or tuple into absolute (x, y) coordinates.

    Args:
        region: (x, y, w, h) bounding box of the matched template.
        position: One of:
            - "center" (default)
            - "top_left", "top_right", "bottom_left", "bottom_right"
            - "top_center", "bottom_center", "left_center", "right_center"
            - (dx, dy) tuple for a custom offset from the top-left corner

    Returns:
        Absolute (x, y) coordinates.
    """
    x, y, w, h = region
    if isinstance(position, (tuple, list)):
        dx, dy = position
        return (x + dx, y + dy)

    pos = position.lower().replace(" ", "_")
    cx = x + w // 2
    cy = y + h // 2

    return {
        "center": (cx, cy),
        "top_left": (x, y),
        "top_center": (cx, y),
        "top_right": (x + w - 1, y),
        "left_center": (x, cy),
        "right_center": (x + w - 1, cy),
        "bottom_left": (x, y + h - 1),
        "bottom_center": (cx, y + h - 1),
        "bottom_right": (x + w - 1, y + h - 1),
    }.get(pos, (cx, cy))


@pytomator_api(
    description="Finds a template on the screen and clicks at the specified position within the matched region.",
    params={
        "name": "Name of the template (must exist in the current project).",
        "button": "Mouse button to use ('primary', 'secondary', 'middle'). Default is 'primary'.",
        "confidence": "Confidence threshold (0.0 to 1.0). If omitted, uses the template's default confidence.",
        "position": "Where to click inside the region. Can be a string like 'center', 'top_left', "
                    "'top_right', 'bottom_left', 'bottom_right', 'top_center', 'bottom_center', "
                    "'left_center', 'right_center', or a tuple (dx, dy) for a custom pixel offset "
                    "from the top-left corner. Default is 'center'.",
        "backend": "Mouse backend: 'standard' (PyAutoGUI) or 'directinput' (Windows only).",
        "autofocus": "If True, focuses the window associated with the template before searching.",
        "smooth_move": "If True, moves gradually to the template before clicking.",
        "move_duration": "Optional smooth movement duration override in seconds.",
        "move_easing": "Optional easing override: linear, ease_out, or ease_in_out.",
    },
    category="Vision",
    returns="True if the template was found and clicked, False otherwise.",
    examples=[
        "click_template('btn_login')",
        "click_template('icon_settings', button='secondary', confidence=0.9)",
        "click_template('btn_ok', position='bottom_right')",
        "click_template('checkbox', position=(5, 5))",
        "click_template('slider', position='left_center')",
        "click_template('play', backend='directinput')  # Windows games/DirectX",
        "click_template('btn_login', autofocus=True)",
        "click_template('target', smooth_move=True)  # Gradual movement for games",
    ],
    version="1.0",
)
def click_template(
    name: str,
    button: str = "primary",
    confidence: Optional[float] = None,
    position: str | tuple[int, int] = "center",
    backend: Optional[str] = None,
    autofocus: Optional[bool] = None,
    smooth_move: bool = False,
    move_duration: Optional[float] = None,
    move_easing: Optional[str] = None,
):
    """Find a template and click at the specified position."""
    from pytomator.core.vision.template_matcher import find_on_screen
    from pytomator.core.vision.capture_tool import (
        get_active_window_info,
    )
    from pytomator.core.vision.search_context import prepare_search_context

    mouse, backend = _mouse_for_backend(backend)
    region, context = _find_template_with_context(name, confidence, autofocus)
    if region is None:
        return False

    # Do not click if another window gained focus after the screenshot.
    if not _window_still_active(context):
        return False

    px, py = _resolve_position(region, position)

    resolved_button = _backend_button(button, backend)
    if smooth_move:
        _move_mouse_to(
            (px, py), backend=backend,
            duration=move_duration, easing=move_easing,
        )
        if not _window_still_active(context):
            return False
    else:
        mouse.moveTo(px, py)
    time.sleep(0.05)
    mouse.mouseDown(button=resolved_button)
    time.sleep(0.05)
    mouse.mouseUp(button=resolved_button)
    return True


@pytomator_api(
    description="Waits until a template appears on screen.",
    params={"name": "Template name.", "timeout": "Maximum wait in seconds.",
            "interval": "Delay between searches.", "confidence": "Optional confidence override.",
            "autofocus": "Focus the associated window before searching."},
    category="Vision", returns="Matched region or None on timeout.",
    examples=["region = wait_for_template('ready', timeout=15)"], version="1.0",
)
def wait_for_template(name: str, timeout: float = 10, interval: float = 0.2,
                      confidence: Optional[float] = None, autofocus: Optional[bool] = None):
    if timeout < 0:
        raise ValueError("timeout must be non-negative")
    if interval < 0:
        raise ValueError("interval must be non-negative")
    deadline = time.monotonic() + timeout
    while True:
        if should_stop():
            raise ScriptInterrupted()
        region = find_template(name, confidence, autofocus)
        if region is not None:
            return region
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        _sleep_interruptibly(min(interval, remaining))


@pytomator_api(
    description="Waits until a template is no longer visible.",
    params={"name": "Template name.", "timeout": "Maximum wait in seconds.",
            "interval": "Delay between searches.", "confidence": "Optional confidence override.",
            "autofocus": "Focus the associated window before searching."},
    category="Vision", returns="True if it disappears, False on timeout.",
    examples=["wait_until_template_disappears('loading')"], version="1.0",
)
def wait_until_template_disappears(name: str, timeout: float = 10,
                                   interval: float = 0.2,
                                   confidence: Optional[float] = None,
                                   autofocus: Optional[bool] = None) -> bool:
    if timeout < 0:
        raise ValueError("timeout must be non-negative")
    if interval < 0:
        raise ValueError("interval must be non-negative")
    deadline = time.monotonic() + timeout
    while True:
        if should_stop():
            raise ScriptInterrupted()
        if find_template(name, confidence, autofocus) is None:
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        _sleep_interruptibly(min(interval, remaining))


@pytomator_api(
    description="Checks whether a template is currently visible.",
    params={"name": "Template name.", "confidence": "Optional confidence override.",
            "autofocus": "Focus the associated window before searching."},
    category="Vision", returns="True when visible.", examples=["if template_exists('save'): ..."],
    version="1.0",
)
def template_exists(name: str, confidence: Optional[float] = None,
                    autofocus: Optional[bool] = None) -> bool:
    return find_template(name, confidence, autofocus) is not None


@pytomator_api(
    description="Finds all visible occurrences of a template.",
    params={"name": "Template name.", "confidence": "Optional confidence override.",
            "autofocus": "Focus the associated window before searching."},
    category="Vision", returns="List of matching regions.",
    examples=["items = find_all_templates('checkbox')"], version="1.0",
)
def find_all_templates(name: str, confidence: Optional[float] = None,
                       autofocus: Optional[bool] = None):
    from pytomator.core.vision.search_context import prepare_search_context
    from pytomator.core.vision.template_matcher import find_all_on_screen

    template = _get_template(name)
    context = prepare_search_context(template, autofocus=autofocus)
    if context is None:
        return []
    return find_all_on_screen(
        template, _get_project_path(), confidence, search_region=context.region
    )


@pytomator_api(
    description="Waits for the first visible template from a list.",
    params={"names": "Template names in priority order.", "timeout": "Maximum wait in seconds.",
            "interval": "Delay between search rounds.", "confidence": "Optional confidence override.",
            "autofocus": "Focus associated windows before searching."},
    category="Vision", returns="Tuple (name, region), or None on timeout.",
    examples=["result = wait_for_any_template(['success', 'error'])"], version="1.0",
)
def wait_for_any_template(names, timeout: float = 10, interval: float = 0.2,
                          confidence: Optional[float] = None,
                          autofocus: Optional[bool] = None):
    names = list(names)
    if not names:
        raise ValueError("names must not be empty")
    if timeout < 0:
        raise ValueError("timeout must be non-negative")
    if interval < 0:
        raise ValueError("interval must be non-negative")
    deadline = time.monotonic() + timeout
    while True:
        if should_stop():
            raise ScriptInterrupted()
        for name in names:
            region = find_template(name, confidence, autofocus)
            if region is not None:
                return name, region
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        _sleep_interruptibly(min(interval, remaining))


@pytomator_api(
    description="Drags a visible template to absolute screen coordinates.",
    params={"name": "Template name.", "x": "Absolute destination X.", "y": "Absolute destination Y.",
            "source_position": "Drag point within the template.", "duration": "Drag duration.",
            "confidence": "Optional confidence override.", "backend": "standard or directinput.",
            "autofocus": "Focus the associated window before searching."},
    category="Vision", returns="True if dragged.", examples=["drag_template_to('card', 500, 300)"],
    version="1.0",
)
def drag_template_to(name: str, x: int, y: int,
                     source_position: str | tuple[int, int] = "center",
                     duration: float = 0.5, confidence: Optional[float] = None,
                     backend: Optional[str] = None, autofocus: Optional[bool] = None) -> bool:
    backend = _resolve_mouse_backend(backend)
    region, context = _find_template_with_context(name, confidence, autofocus)
    if region is None or not _window_still_active(context):
        return False
    _mouse_drag(_resolve_position(region, source_position), (x, y), duration, backend)
    return True


@pytomator_api(
    description="Drags one visible template onto another.",
    params={"source": "Source template.", "target": "Target template.",
            "source_position": "Drag point in source.", "target_position": "Drop point in target.",
            "duration": "Drag duration.", "confidence": "Optional confidence override.",
            "backend": "standard or directinput.", "autofocus": "Focus associated windows."},
    category="Vision", returns="True if both templates were found and dragged.",
    examples=["drag_template_to_template('file', 'folder')"], version="1.0",
)
def drag_template_to_template(source: str, target: str,
                              source_position: str | tuple[int, int] = "center",
                              target_position: str | tuple[int, int] = "center",
                              duration: float = 0.5,
                              confidence: Optional[float] = None,
                              backend: Optional[str] = None,
                              autofocus: Optional[bool] = None) -> bool:
    backend = _resolve_mouse_backend(backend)
    source_region, source_context = _find_template_with_context(
        source, confidence, autofocus
    )
    if source_region is None:
        return False
    target_region, target_context = _find_template_with_context(
        target, confidence, autofocus
    )
    if target_region is None or not _window_still_active(target_context):
        return False
    source_id = source_context.window.get("id")
    target_id = target_context.window.get("id")
    if source_id is not None and target_id is not None and source_id != target_id:
        return False
    _mouse_drag(
        _resolve_position(source_region, source_position),
        _resolve_position(target_region, target_position),
        duration, backend,
    )
    return True


@pytomator_api(
    description="Clicks at an offset relative to a visible template's top-left corner.",
    params={"name": "Template name.", "dx": "Horizontal offset.", "dy": "Vertical offset.",
            "button": "Mouse button.", "confidence": "Optional confidence override.",
            "backend": "standard or directinput.", "autofocus": "Focus associated window."},
    category="Vision", returns="True if clicked.",
    examples=["click_relative_to_template('label_email', 180, 10)"], version="1.0",
)
def click_relative_to_template(name: str, dx: int, dy: int,
                               button: str = "primary",
                               confidence: Optional[float] = None,
                               backend: Optional[str] = None,
                               autofocus: Optional[bool] = None) -> bool:
    return click_template(
        name, button=button, confidence=confidence, position=(dx, dy),
        backend=backend, autofocus=autofocus,
    )


@pytomator_api(
    description="Scrolls until a template becomes visible or the limit is reached.",
    params={"name": "Template name.", "direction": "up or down.",
            "max_scrolls": "Maximum scroll attempts.", "amount": "Units per scroll.",
            "interval": "Delay after each scroll.", "confidence": "Optional confidence override.",
            "autofocus": "Focus associated window before searching.",
            "backend": "Optional mouse backend override."},
    category="Vision", returns="Matched region or None.",
    examples=["region = scroll_until_template('footer', direction='down')"], version="1.0",
)
def scroll_until_template(name: str, direction: str = "down",
                          max_scrolls: int = 20, amount: int = 3,
                          interval: float = 0.2,
                          confidence: Optional[float] = None,
                          autofocus: Optional[bool] = None,
                          backend: Optional[str] = None):
    direction = direction.lower()
    if direction not in {"up", "down"}:
        raise ValueError("direction must be 'up' or 'down'")
    if max_scrolls < 0:
        raise ValueError("max_scrolls must be non-negative")
    if amount <= 0:
        raise ValueError("amount must be positive")
    if interval < 0:
        raise ValueError("interval must be non-negative")
    for attempt in range(max_scrolls + 1):
        if should_stop():
            raise ScriptInterrupted()
        region = find_template(name, confidence, autofocus)
        if region is not None:
            return region
        if attempt == max_scrolls:
            return None
        mouse, _ = _mouse_for_backend(backend)
        mouse.scroll(amount if direction == "up" else -amount)
        _sleep_interruptibly(interval)


@pytomator_api(
    description="Finds a template and moves the mouse gradually to a position within it.",
    params={
        "name": "Template name.",
        "confidence": "Optional confidence override.",
        "position": "Destination within the matched region.",
        "autofocus": "Focus the associated window before searching.",
        "duration": "Optional movement duration override in seconds.",
        "easing": "Optional easing override: linear, ease_out, or ease_in_out.",
        "backend": "Optional mouse backend override.",
    },
    category="Vision",
    returns="True if the template was found and the mouse moved, False otherwise.",
    examples=[
        "move_to_template('btn_login')",
        "move_to_template('target', duration=0.5, easing='ease_in_out')",
    ],
    version="1.0",
)
def move_to_template(
    name: str,
    confidence: Optional[float] = None,
    position: str | tuple[int, int] = "center",
    autofocus: Optional[bool] = None,
    duration: Optional[float] = None,
    easing: Optional[str] = None,
    backend: Optional[str] = None,
) -> bool:
    """Find a template and move gradually to the specified position."""
    region, context = _find_template_with_context(name, confidence, autofocus)
    if region is None or not _window_still_active(context):
        return False
    _move_mouse_to(
        _resolve_position(region, position),
        backend=backend,
        duration=duration,
        easing=easing,
    )
    return _window_still_active(context)


@pytomator_api(
    description="Finds a template on the screen and moves the mouse to the specified position within the matched region.",
    params={
        "name": "Name of the template (must exist in the current project).",
        "confidence": "Confidence threshold (0.0 to 1.0). If omitted, uses the template's default confidence.",
        "position": "Where to hover inside the region. Same options as click_template. Default is 'center'.",
        "autofocus": "If True, focuses the window associated with the template before searching.",
        "smooth_move": "If True, moves gradually instead of teleporting.",
        "move_duration": "Optional smooth movement duration override in seconds.",
        "move_easing": "Optional easing override: linear, ease_out, or ease_in_out.",
        "backend": "Optional mouse backend override.",
    },
    category="Vision",
    returns="True if the template was found and hovered, False otherwise.",
    examples=[
        "hover_template('btn_login')",
        "hover_template('icon_settings', confidence=0.9)",
        "hover_template('slider', position='right_center')",
        "hover_template('btn_login', autofocus=True)",
        "hover_template('target', smooth_move=True)",
    ],
    version="1.0",
)
def hover_template(
    name: str,
    confidence: Optional[float] = None,
    position: str | tuple[int, int] = "center",
    autofocus: Optional[bool] = None,
    backend: Optional[str] = None,
    smooth_move: bool = False,
    move_duration: Optional[float] = None,
    move_easing: Optional[str] = None,
):
    """Find a template and move the mouse to the specified position."""
    from pytomator.core.vision.template_matcher import find_on_screen
    from pytomator.core.vision.capture_tool import get_active_window_info
    from pytomator.core.vision.search_context import prepare_search_context

    template = _get_template(name)
    project_path = _get_project_path()
    context = prepare_search_context(template, autofocus=autofocus)
    if context is None:
        return False
    region = find_on_screen(
        template,
        project_path,
        confidence,
        search_region=context.region,
        debug=_vision_debug_enabled(),
        window_info=context.window,
    )
    if region is None:
        return False
    window_id = context.window.get("id")
    if window_id is not None and get_active_window_info().get("id") != window_id:
        return False
    px, py = _resolve_position(region, position)
    if smooth_move:
        _move_mouse_to(
            (px, py), backend=backend,
            duration=move_duration, easing=move_easing,
        )
        if not _window_still_active(context):
            return False
    else:
        mouse, _ = _mouse_for_backend(backend)
        mouse.moveTo(px, py)
    return True

@pytomator_api(
    description="Enables or disables the use of pydirectinput for keys. Useful on Windows to avoid security blocks.",
    params={"state": "If True, uses pydirectinput; if False, uses pyautogui. Default is True on Windows, False on other systems."},
    returns=None,
    examples=[
        "direct_input_keys(True)  # Uses pydirectinput",
        "direct_input_keys(False) # Uses pyautogui",
    ],
    version="1.0",
)
def direct_input_keys( state: bool = True):
    global use_direct_input_keys
    use_direct_input_keys = state

@pytomator_api(
    description="Waits for 'seconds', which can be interrupted.",
    params={
        "seconds": "Number of seconds to wait.",
        "check_interval": "Interval in seconds to check for interruptions (default 0.05)."
    },
    returns=None,
    examples=[
        "wait(2)  # Waits for 2 seconds",
        "wait(5, check_interval=0.1)  # Waits for 5 seconds, checking interruptions every 0.1s",
    ],
    version="1.0",
)
def wait(seconds: float = 1, check_interval: float = 0.05):
    """
    Espera por 'seconds', podendo ser interrompido.
    """
    end_time = time.monotonic() + seconds

    while time.monotonic() < end_time:
        # 🔥 interrupção cooperativa
        if should_stop():
            raise ScriptInterrupted()

        remaining = end_time - time.monotonic()
        time.sleep(min(check_interval, max(0, remaining)))

@pytomator_api(
    description="Checks if the script should be interrupted, raising ScriptInterrupted if so.",
    params={},
    returns=None,
    examples=[
        "check_interruption()  # Raises ScriptInterrupted if the script should be interrupted",
    ],
    version="1.0",
)
def check_interruption():
    if should_stop():
        raise ScriptInterrupted()

@pytomator_api(
    description="Clicks at position (x, y). If x or y is None, clicks at the current mouse position.",
    params={
        "button": "Mouse button to use ('primary', 'secondary', 'middle'). Default is 'primary'. Accepts left, right, middle.",
        "x": "X coordinate to click. If None, uses the current mouse position.",
        "y": "Y coordinate to click. If None, uses the current mouse position.",
        "backend": "Optional mouse backend override.",
    },
    category="Mouse",
    returns=None,
    examples=[
        "click('primary', 100, 200)  # Clicks primary button at (100, 200)",
        "click('secondary')          # Clicks secondary button at the current position",
        "click('middle', 300, 400)   # Clicks middle button at (300, 400)",
        "click()                     # Clicks primary button at the current position",
    ],
    version="1.0",
)
def click(button="primary", x=None, y=None, backend: Optional[str] = None):
    mouse, resolved_backend = _mouse_for_backend(backend)
    button = _backend_button(button, resolved_backend)
    if x is None or y is None:
        mouse.click(button=button)
    else:
        mouse.click(x, y, button=button)
        
@pytomator_api(
    description=
        "Holds a mouse click for 'duration' seconds at position (x, y). \
            If x or y is None, holds at the current mouse position.",
    params={
        "duration": "Duration in seconds to hold the click.",
        "button": "Mouse button to use ('primary', 'secondary', 'middle'). Default is 'primary'. Accepts left, right, middle.",
        "x": "X coordinate to hold the click. If None, uses the current mouse position.",
        "y": "Y coordinate to hold the click. If None, uses the current mouse position.",
        "backend": "Optional mouse backend override.",
    },
    category="Mouse",
    returns=None,
    examples=[
        "click_hold(2, 'primary', 100, 200)  # Holds a primary click at (100, 200) for 2 seconds",
        "click_hold(1.5)                     # Holds a primary click at the current position for 1.5 seconds",
        "click_hold(3, 'secondary')          # Holds a secondary click at the current position for 3 seconds",
    ],
    version="1.0",
)
def click_hold(duration=1, button="primary", x=None, y=None, backend: Optional[str] = None):
    mouse, resolved_backend = _mouse_for_backend(backend)
    button = _backend_button(button, resolved_backend)
    mouse.mouseDown(x, y, button=button)
    wait(duration)
    mouse.mouseUp(x, y, button=button)

@pytomator_api(
    description=
        "Performs multiple clicks at position (x, y) with a specified interval between clicks. \
            If x or y is None, clicks at the current mouse position.",
    params={
        "button": "Mouse button to use ('primary', 'secondary', 'middle'). Default is 'primary'. Accepts left, right, middle.",
        "x": "X coordinate to click. If None, uses the current mouse position.",
        "y": "Y coordinate to click. If None, uses the current mouse position.",
        "clicks": "Number of clicks to perform.",
        "interval": "Interval in seconds between clicks. Accepts float values.",
        "backend": "Optional mouse backend override.",
    },
    category="Mouse",
    returns=None,
    examples=[
        "clicks('primary', 100, 200, clicks=3, interval=0.2)  # Clicks primary button 3 times at (100, 200) with 0.2s interval",
        "clicks(clicks=5)                                    # Clicks primary button 5 times at the current position with default interval",
        "clicks('secondary', clicks=2, interval=0.1)         # Clicks secondary button 2 times at the current position with 0.1s interval",
    ],
    version="1.0",
)
def clicks(button="primary", x=None, y=None, clicks=1, interval=0.5,
           backend: Optional[str] = None):
    mouse, resolved_backend = _mouse_for_backend(backend)
    mouse.click(
        x, y, clicks=clicks, interval=interval,
        button=_backend_button(button, resolved_backend),
    )

@pytomator_api(
    description="Holds a key down for 'duration' seconds.",
    params={
        "key": "The key to hold down (e.g., 'a', 'enter', 'shift').",
        "duration": "Duration in seconds to hold the key down.",
    },
    category="Keyboard",
    returns=None,
    examples=[
        "hold('a', duration=2)      # Holds the 'a' key down for 2 seconds",
        "hold('enter', duration=1)  # Holds the 'enter' key down for 1 second",
    ],
    version="1.0",
)
def hold(key, duration=1):
    if use_direct_input_keys:
        pydirectinput.keyDown(key)
        wait(duration)
        pydirectinput.keyUp(key)
        return
    pyautogui.keyDown(key)
    wait(duration)
    pyautogui.keyUp(key)

@pytomator_api(
    description="Presses a key. It chooses between pydirectinput and pyautogui based on the platform and settings.",
    params={
        "key": "The key to press (e.g., 'a', 'enter', 'shift').",
    },
    category="Keyboard",
    returns=None,
    examples=[
        "press('a')      # Presses the 'a' key",
        "press('enter')  # Presses the 'enter' key",
    ],
    version="1.0",
)
def press(key):
    if use_direct_input_keys:
        pydirectinput.press(key)
        return
    pyautogui.press(key)

@pytomator_api(
    description="Writes text with an optional interval between each character.",
    params={
        "text": "The text to write.",
        "interval": "Interval in seconds between each character (default is 0.05).",
    },
    category="Keyboard",
    returns=None,
    examples=[
        "write('Hello, World!', interval=0.1)  # Writes 'Hello, World!' with 0.1s interval between characters",
        "write('Quick text')                    # Writes 'Quick text' with default interval",
    ],
    version="1.0",
)
def write(text, interval=0.05):
    pyautogui.write(text, interval=interval)


# ═══════════════════════════════════════════════════════════════
# Project script importing (available only when a project is open)
# ═══════════════════════════════════════════════════════════════

@pytomator_api(
    description="Imports a script from the current project into the running script's namespace. "
                "Results are cached for the current run cycle, so the script code is executed only once.",
    params={
        "name": "The name of the script to import (must exist in the current project).",
        "merge": "If True, injects all definitions into the calling script's global scope (default False)."
    },
    returns="A namespace-like object with the script's top-level definitions accessible as attributes.",
    category="Project",
    examples=[
        "utils = import_script('utils')        # Import as namespace",
        "utils.login()                         # Call via namespace",
        "import_script('vars', merge=True)     # Inject into global scope",
        "soma(a, b)                            # Use directly after merge",
    ],
    version="1.0",
)
def import_script(name: str, merge: bool = False):
    """Import a script from the current project (cached per run cycle)."""
    global _import_cache

    if name in _import_cache and not merge:
        return _import_cache[name]

    if _project_manager is None or not _project_manager.is_project_open:
        raise NameError(f"No project is currently open — cannot import script '{name}'")

    script = _project_manager.get_script(name)
    if script is None:
        raise NameError(f"Script '{name}' not found in the current project")

    ns: dict = {}
    exec(script.code, ns)
    wrapper = _ScriptNamespace(ns)
    _import_cache[name] = wrapper

    # If merge=True, inject all definitions into the caller's global scope
    if merge:
        import sys
        caller_globals = sys._getframe(1).f_globals
        for key, value in ns.items():
            if not key.startswith("_"):  # Skip private names
                caller_globals[key] = value

    return wrapper


@pytomator_api(
    description="Imports a script from the current project, forcing re-execution even if it was cached earlier.",
    params={
        "name": "The name of the script to reload (must exist in the current project).",
        "merge": "If True, injects all definitions into the calling script's global scope (default False)."
    },
    returns="A namespace-like object with the script's top-level definitions accessible as attributes.",
    category="Project",
    examples=[
        "utils = reload_script('utils')            # Re-import ignoring cache",
        "reload_script('vars', merge=True)          # Re-import and inject",
    ],
    version="1.0",
)
def reload_script(name: str, merge: bool = False):
    """Import a script from the current project, forcing a reload."""
    global _import_cache

    if _project_manager is None or not _project_manager.is_project_open:
        raise NameError(f"No project is currently open — cannot reload script '{name}'")

    script = _project_manager.get_script(name)
    if script is None:
        raise NameError(f"Script '{name}' not found in the current project")

    ns: dict = {}
    exec(script.code, ns)
    wrapper = _ScriptNamespace(ns)
    _import_cache[name] = wrapper  # Update cache

    # If merge=True, inject all definitions into the caller's global scope
    if merge:
        import sys
        caller_globals = sys._getframe(1).f_globals
        for key, value in ns.items():
            if not key.startswith("_"):
                caller_globals[key] = value

    return wrapper
