import keyboard


class HotkeyManager:
    def __init__(self):
        self._hotkey = None

    def register(self, hotkey, callback):
        if self._hotkey:
            keyboard.remove_hotkey(self._hotkey)

        self._hotkey = keyboard.add_hotkey(hotkey, callback)

    def unregister(self):
        if self._hotkey:
            keyboard.remove_hotkey(self._hotkey)
            self._hotkey = None
