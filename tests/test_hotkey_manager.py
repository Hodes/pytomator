import sys
import unittest
from unittest.mock import MagicMock, patch

from pytomator.core import hotkey_backends
from pytomator.core.hotkey_manager import HotkeyManager


@unittest.skipUnless(sys.platform == "win32", "Windows native hotkeys only")
class WindowsNativeHotkeyTests(unittest.TestCase):
    def test_f5_uses_no_repeat(self):
        modifiers, vk = hotkey_backends.parse_windows_hotkey("f5")
        self.assertTrue(modifiers & hotkey_backends.MOD_NOREPEAT)
        self.assertEqual(vk, 0x74)

    def test_native_failure_uses_hook_fallback(self):
        native = MagicMock(); native.register.side_effect = OSError("busy")
        fallback = MagicMock(); fallback.register.return_value = 123
        manager = HotkeyManager.__new__(HotkeyManager)
        manager._registered_hotkeys = {}; manager._action_by_hotkey = {}
        manager._native = native; manager._fallback = fallback; manager.fallback_actions = set()
        callback = MagicMock()
        manager.register("recording_test", "f5", callback)
        fallback.register.assert_called_once_with("f5", callback)
        self.assertIn("recording_test", manager.fallback_actions)


if __name__ == "__main__":
    unittest.main()
