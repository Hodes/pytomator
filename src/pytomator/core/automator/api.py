import sys
import time
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
    autofocus: bool = False,
):
    """Find a template on the screen and return its bounding box."""
    from pytomator.core.vision.template_matcher import find_on_screen
    from pytomator.core.vision.search_context import prepare_search_context

    template = _get_template(name)
    project_path = _get_project_path()
    context = prepare_search_context(template, autofocus=autofocus)
    if context is None:
        return None
    result = find_on_screen(
        template,
        project_path,
        confidence,
        search_region=context.region,
        debug=_vision_debug_enabled(),
        window_info=context.window,
    )
    return result


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
    ],
    version="1.0",
)
def click_template(
    name: str,
    button: str = "primary",
    confidence: Optional[float] = None,
    position: str | tuple[int, int] = "center",
    backend: str = "standard",
    autofocus: bool = False,
):
    """Find a template and click at the specified position."""
    from pytomator.core.vision.template_matcher import find_on_screen
    from pytomator.core.vision.capture_tool import (
        get_active_window_info,
    )
    from pytomator.core.vision.search_context import prepare_search_context

    backend = backend.lower()
    if backend not in {"standard", "directinput"}:
        raise ValueError("backend must be 'standard' or 'directinput'")
    if backend == "directinput" and sys.platform != "win32":
        raise RuntimeError("The directinput mouse backend is available only on Windows")

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

    # Do not click if another window gained focus after the screenshot.
    window_id = context.window.get("id")
    if window_id is not None and get_active_window_info().get("id") != window_id:
        return False

    px, py = _resolve_position(region, position)

    if backend == "directinput":
        direct_button = {"primary": "left", "secondary": "right"}.get(button, button)
        pydirectinput.moveTo(px, py)
        pydirectinput.mouseDown(button=direct_button)
        pydirectinput.mouseUp(button=direct_button)
    else:
        pyautogui.moveTo(px, py)
        pyautogui.mouseDown(button=button)
        pyautogui.mouseUp(button=button)
    return True


@pytomator_api(
    description="Finds a template on the screen and moves the mouse to the specified position within the matched region.",
    params={
        "name": "Name of the template (must exist in the current project).",
        "confidence": "Confidence threshold (0.0 to 1.0). If omitted, uses the template's default confidence.",
        "position": "Where to hover inside the region. Same options as click_template. Default is 'center'.",
        "autofocus": "If True, focuses the window associated with the template before searching.",
    },
    category="Vision",
    returns="True if the template was found and hovered, False otherwise.",
    examples=[
        "hover_template('btn_login')",
        "hover_template('icon_settings', confidence=0.9)",
        "hover_template('slider', position='right_center')",
        "hover_template('btn_login', autofocus=True)",
    ],
    version="1.0",
)
def hover_template(
    name: str,
    confidence: Optional[float] = None,
    position: str | tuple[int, int] = "center",
    autofocus: bool = False,
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
    pyautogui.moveTo(px, py)
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
def click(button="primary", x=None, y=None):
    if x is None or y is None:
        pyautogui.click(button=button)
    else:
        pyautogui.click(x, y, button=button)
        
@pytomator_api(
    description=
        "Holds a mouse click for 'duration' seconds at position (x, y). \
            If x or y is None, holds at the current mouse position.",
    params={
        "duration": "Duration in seconds to hold the click.",
        "button": "Mouse button to use ('primary', 'secondary', 'middle'). Default is 'primary'. Accepts left, right, middle.",
        "x": "X coordinate to hold the click. If None, uses the current mouse position.",
        "y": "Y coordinate to hold the click. If None, uses the current mouse position.",
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
def click_hold(duration=1, button="primary", x=None, y=None):
    pyautogui.mouseDown(x, y, button=button)
    wait(duration)
    pyautogui.mouseUp(x, y, button=button)

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
def clicks(button="primary", x=None, y=None, clicks=1, interval=0.5):
    pyautogui.click(x, y, clicks=clicks, interval=interval, button=button)

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
