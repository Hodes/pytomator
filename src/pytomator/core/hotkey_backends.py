"""Platform hotkey backends, preferring native Windows WM_HOTKEY."""

import ctypes
import logging
import sys
from ctypes import wintypes

import keyboard


class KeyboardHookBackend:
    name = "keyboard-hook"

    def register(self, hotkey: str, callback):
        return keyboard.add_hotkey(hotkey, callback)

    def unregister(self, handle):
        keyboard.remove_hotkey(handle)


if sys.platform == "win32":
    from PyQt6.QtCore import QAbstractNativeEventFilter
    from PyQt6.QtWidgets import QApplication

    WM_HOTKEY = 0x0312
    MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 1, 2, 4, 8, 0x4000
    MODIFIERS = {
        "alt": MOD_ALT, "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
        "shift": MOD_SHIFT, "win": MOD_WIN, "windows": MOD_WIN,
    }
    SPECIAL_KEYS = {
        "space": 0x20, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
        "esc": 0x1B, "escape": 0x1B, "backspace": 0x08, "delete": 0x2E,
        "insert": 0x2D, "home": 0x24, "end": 0x23, "pageup": 0x21,
        "pagedown": 0x22, "left": 0x25, "up": 0x26, "right": 0x27,
        "down": 0x28,
    }

    def parse_windows_hotkey(hotkey: str) -> tuple[int, int]:
        parts = [part.strip().lower() for part in hotkey.split("+") if part.strip()]
        modifiers = MOD_NOREPEAT
        keys = []
        for part in parts:
            if part in MODIFIERS:
                modifiers |= MODIFIERS[part]
            else:
                keys.append(part)
        if len(keys) != 1:
            raise ValueError(f"Unsupported native hotkey: {hotkey}")
        key = keys[0]
        if len(key) == 1 and key.isalnum():
            vk = ord(key.upper())
        elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
            vk = 0x70 + int(key[1:]) - 1
        elif key in SPECIAL_KEYS:
            vk = SPECIAL_KEYS[key]
        else:
            raise ValueError(f"Unsupported native hotkey key: {key}")
        return modifiers, vk

    class WindowsNativeHotkeyBackend(QAbstractNativeEventFilter):
        name = "windows-native"

        def __init__(self):
            super().__init__()
            self._next_id = 0x5000
            self._callbacks = {}
            app = QApplication.instance()
            if app is None:
                raise RuntimeError("QApplication must exist before registering hotkeys")
            app.installNativeEventFilter(self)

        def register(self, hotkey: str, callback):
            modifiers, vk = parse_windows_hotkey(hotkey)
            hotkey_id = self._next_id; self._next_id += 1
            if not ctypes.windll.user32.RegisterHotKey(None, hotkey_id, modifiers, vk):
                raise OSError(ctypes.get_last_error(), f"RegisterHotKey failed for '{hotkey}'")
            self._callbacks[hotkey_id] = callback
            logging.getLogger(__name__).info("Registered native hotkey %s as id %s", hotkey, hotkey_id)
            return hotkey_id

        def unregister(self, handle):
            self._callbacks.pop(handle, None)
            ctypes.windll.user32.UnregisterHotKey(None, handle)

        def nativeEventFilter(self, event_type, message):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                callback = self._callbacks.get(int(msg.wParam))
                if callback:
                    logging.getLogger(__name__).debug("Native hotkey id %s triggered", msg.wParam)
                    callback()
                    return True, 0
            return False, 0
else:
    WindowsNativeHotkeyBackend = None
