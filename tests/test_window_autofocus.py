import sys
import unittest
from unittest.mock import MagicMock, patch

from pytomator.core.vision.models import TemplateCapture
from pytomator.core.vision.search_context import prepare_search_context
from pytomator.core.windows.windows_window_controller import WindowsWindowController


def make_template(title="Target"):
    return TemplateCapture(
        name="button",
        image_path="templates/button.png",
        region_abs=(0, 0, 10, 10),
        active_window_title=title,
    )


class WindowsWindowControllerTests(unittest.TestCase):
    def _win32gui(self, windows):
        gui = MagicMock()
        gui.EnumWindows.side_effect = lambda callback, extra: [
            callback(hwnd, extra) for hwnd in windows
        ]
        gui.IsWindowVisible.side_effect = lambda hwnd: windows[hwnd]["visible"]
        gui.GetWindowText.side_effect = lambda hwnd: windows[hwnd]["title"]
        gui.GetWindowRect.side_effect = lambda hwnd: windows[hwnd]["rect"]
        return gui

    def test_prefers_case_insensitive_exact_match_then_partial(self):
        windows = {
            1: {"visible": True, "title": "Target - document", "rect": (0, 0, 100, 100)},
            2: {"visible": True, "title": "TARGET", "rect": (10, 20, 110, 120)},
        }
        gui = self._win32gui(windows)
        with patch.dict(sys.modules, {"win32gui": gui}):
            result = WindowsWindowController().find_window("target")
        self.assertEqual(result["id"], 2)

        windows[2]["title"] = "Another app"
        with patch.dict(sys.modules, {"win32gui": gui}):
            result = WindowsWindowController().find_window("target")
        self.assertEqual(result["id"], 1)

    def test_ignores_invisible_and_empty_title_windows(self):
        windows = {
            1: {"visible": False, "title": "Target", "rect": (0, 0, 10, 10)},
            2: {"visible": True, "title": "", "rect": (0, 0, 10, 10)},
        }
        with patch.dict(sys.modules, {"win32gui": self._win32gui(windows)}):
            self.assertIsNone(WindowsWindowController().find_window("target"))

    def test_restores_minimized_window_and_confirms_focus(self):
        gui = MagicMock()
        gui.IsWindow.return_value = True
        gui.IsIconic.return_value = True
        gui.GetForegroundWindow.return_value = 42
        con = MagicMock(SW_RESTORE=9)
        with patch.dict(sys.modules, {"win32gui": gui, "win32con": con}):
            focused = WindowsWindowController().focus_window({"id": 42})
        self.assertTrue(focused)
        gui.ShowWindow.assert_called_once_with(42, 9)
        gui.SetForegroundWindow.assert_called_once_with(42)

    def test_reports_failure_when_focus_is_not_granted(self):
        gui = MagicMock()
        gui.IsWindow.return_value = True
        gui.IsIconic.return_value = False
        gui.GetForegroundWindow.return_value = 99
        with patch.dict(sys.modules, {"win32gui": gui, "win32con": MagicMock()}):
            self.assertFalse(WindowsWindowController().focus_window({"id": 42}))


class SearchContextTests(unittest.TestCase):
    @patch("pytomator.core.vision.search_context.get_window_controller")
    @patch("pytomator.core.vision.capture_tool.get_active_window_info")
    @patch("pytomator.core.vision.capture_tool.get_active_search_region")
    def test_autofocus_uses_focused_window_region(
        self, get_region, get_active_window, get_controller
    ):
        window = {"id": 7, "title": "Target", "left": 1, "top": 2, "width": 3, "height": 4}
        controller = get_controller.return_value
        controller.find_window.return_value = window
        controller.focus_window.return_value = True
        get_active_window.return_value = window
        region = {"left": 1, "top": 2, "width": 3, "height": 4}
        get_region.return_value = (region, window)

        context = prepare_search_context(make_template(), autofocus=True)

        self.assertEqual(context.region, region)
        self.assertIs(context.window, window)
        get_region.assert_called_once_with(window)

    @patch("pytomator.core.vision.search_context.get_window_controller")
    def test_autofocus_fails_closed_without_title_window_or_focus(self, get_controller):
        self.assertIsNone(prepare_search_context(make_template(None), autofocus=True))
        get_controller.return_value = None
        self.assertIsNone(prepare_search_context(make_template(), autofocus=True))
        controller = MagicMock()
        get_controller.return_value = controller
        controller.find_window.return_value = None
        self.assertIsNone(prepare_search_context(make_template(), autofocus=True))
        controller.find_window.return_value = {"id": 1}
        controller.focus_window.return_value = False
        self.assertIsNone(prepare_search_context(make_template(), autofocus=True))

    @patch("pytomator.core.vision.capture_tool.get_active_search_region")
    def test_without_autofocus_keeps_active_window_behavior(self, get_region):
        active = {"id": 3}
        region = {"left": 0, "top": 0, "width": 100, "height": 100}
        get_region.return_value = (region, active)
        context = prepare_search_context(make_template(), autofocus=False)
        self.assertEqual(context.region, region)
        get_region.assert_called_once_with(None)

    @patch("pytomator.core.vision.capture_tool.get_active_search_region")
    def test_explicit_false_overrides_template_autofocus(self, get_region):
        template = make_template()
        template.autofocus = True
        get_region.return_value = ({"left": 0, "top": 0, "width": 10, "height": 10}, {"id": 1})

        context = prepare_search_context(template, autofocus=False)

        self.assertIsNotNone(context)
        get_region.assert_called_once_with(None)

    @patch("pytomator.core.vision.search_context.get_window_controller")
    def test_omitted_autofocus_uses_template_default(self, get_controller):
        template = make_template()
        template.autofocus = True
        get_controller.return_value = None

        self.assertIsNone(prepare_search_context(template))
        get_controller.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
