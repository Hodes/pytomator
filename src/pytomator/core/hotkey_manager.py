import keyboard


class HotkeyManager:
    def __init__(self):
        self._registered_hotkeys = {}  # action -> handler_id
        self._action_by_hotkey = {}    # hotkey_string -> action

    def register(self, action, hotkey, callback):
        self.unregister(action)
        # Remove old mapping if exists
        if hotkey in self._action_by_hotkey:
            old_action = self._action_by_hotkey[hotkey]
            self.unregister(old_action)
        handler_id = keyboard.add_hotkey(hotkey, callback)
        self._registered_hotkeys[action] = handler_id
        self._action_by_hotkey[hotkey] = action

    def unregister(self, action):
        handler_id = self._registered_hotkeys.pop(action, None)
        if handler_id:
            keyboard.remove_hotkey(handler_id)
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