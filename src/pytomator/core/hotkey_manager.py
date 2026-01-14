import keyboard


class HotkeyManager:
    def __init__(self):
        self._registered_hotkeys = {}

    def register(self, action, hotkey, callback):
        self.unregister(action)
        self._registered_hotkeys[action] = keyboard.add_hotkey(hotkey, callback)

    def unregister(self, action):
        if self._registered_hotkeys.get(action):
            keyboard.remove_hotkey(self._registered_hotkeys[action])
            del self._registered_hotkeys[action]
