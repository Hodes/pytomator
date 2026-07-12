"""Safe bridge between persisted recording commands and the public API."""

import inspect
from typing import Any

from pytomator.core.api_registry import API_REGISTRY, ApiFunction
from pytomator.core.automator import api as automator_api  # populate registry


ALLOWED_API_COMMANDS = {
    "wait", "click", "click_hold", "clicks", "hold", "press", "write",
    "key_down", "key_up", "key_down_physical", "key_up_physical", "hotkey",
    "mouse_down", "mouse_up", "move_to", "scroll",
}


def available_commands() -> list[ApiFunction]:
    return sorted(
        (value for name, value in API_REGISTRY.items() if name in ALLOWED_API_COMMANDS and not value.deprecated),
        key=lambda value: (value.category, value.name),
    )


def validate_call(name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
    if name not in ALLOWED_API_COMMANDS or name not in API_REGISTRY:
        return False, f"API command '{name}' is unavailable"
    try:
        inspect.signature(API_REGISTRY[name].func).bind(**arguments)
    except TypeError as exc:
        return False, str(exc)
    if not _json_value(arguments):
        return False, "Arguments must contain only JSON-compatible values"
    return True, ""


def execute(name: str, arguments: dict[str, Any]):
    valid, error = validate_call(name, arguments)
    if not valid:
        raise ValueError(error)
    return API_REGISTRY[name].func(**arguments)


def _json_value(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _json_value(item) for key, item in value.items())
    return False
