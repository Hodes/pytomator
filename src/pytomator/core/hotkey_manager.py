import logging
import sys

from pytomator.core.hotkey_backends import KeyboardHookBackend, WindowsNativeHotkeyBackend


class HotkeyManager:
    def __init__(self):
        self._registered_hotkeys = {}  # action -> (backend, handler_id)
        self._action_by_hotkey = {}    # hotkey_string -> action
        self._fallback = KeyboardHookBackend()
        self._native = WindowsNativeHotkeyBackend() if sys.platform == "win32" else None
        self.fallback_actions = set()

    def register(self, action, hotkey, callback):
        self.unregister(action)
        # Remove old mapping if exists
        if hotkey in self._action_by_hotkey:
            old_action = self._action_by_hotkey[hotkey]
            self.unregister(old_action)
        backend = self._native or self._fallback
        try:
            handler_id = backend.register(hotkey, callback)
            self.fallback_actions.discard(action)
        except Exception as exc:
            if backend is self._fallback:
                raise
            logging.getLogger(__name__).warning("Native hotkey failed; using hook fallback: %s", exc)
            backend = self._fallback
            handler_id = backend.register(hotkey, callback)
            self.fallback_actions.add(action)
        self._registered_hotkeys[action] = (backend, handler_id)
        self._action_by_hotkey[hotkey] = action

    def unregister(self, action):
        registration = self._registered_hotkeys.pop(action, None)
        if registration:
            backend, handler_id = registration
            backend.unregister(handler_id)
        self.fallback_actions.discard(action)
        # Remove from reverse map
        for hotkey, act in list(self._action_by_hotkey.items()):
            if act == action:
                del self._action_by_hotkey[hotkey]
                break

    def clear_all(self):
        """Unregister all hotkeys."""
        for action in list(self._registered_hotkeys.keys()):
            self.unregister(action)

    def hotkey_in_use(self, hotkey: str) -> bool:
        """Check if a hotkey string is already registered."""
        return hotkey in self._action_by_hotkey

    def get_action_for_hotkey(self, hotkey: str):
        """Return the action name associated with a hotkey, or None."""
        return self._action_by_hotkey.get(hotkey)
