import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent, QPixmap
from PyQt6.QtWidgets import QApplication

from pytomator.ui.capture.capture_manager import CaptureManager
from pytomator.ui.capture.capture_overlay import CapturePreviewDialog


class CaptureCancellationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        project_manager = SimpleNamespace(is_project_open=True)
        self.manager = CaptureManager(project_manager)
        self.main_window = MagicMock()
        self.manager.set_main_window(self.main_window)

    def test_cancel_closes_all_overlays_and_emits_once(self):
        first = MagicMock()
        second = MagicMock()
        self.manager._capture_active = True
        self.manager._overlay = second
        self.manager._overlays = {first, second}
        cancelled = MagicMock()
        self.manager.capture_cancelled.connect(cancelled)

        self.manager.cancel_capture()
        self.manager.cancel_capture()

        first.close.assert_called_once_with()
        second.close.assert_called_once_with()
        self.assertEqual(cancelled.call_count, 1)
        self.assertFalse(self.manager._overlays)
        self.main_window.showNormal.assert_called_once_with()

    def test_start_capture_replaces_existing_workflow(self):
        stale_overlay = MagicMock()
        self.manager._capture_active = True
        self.manager._overlay = stale_overlay
        self.manager._overlays = {stale_overlay}

        with patch.object(self.manager, "_show_overlay") as show_overlay:
            self.manager.start_capture()

        stale_overlay.close.assert_called_once_with()
        self.assertTrue(self.manager._capture_active)
        show_overlay.assert_called_once_with()

    def test_escape_in_preview_requests_global_cancellation(self):
        dialog = CapturePreviewDialog(
            QPixmap(10, 10),
            0,
            0,
            10,
            10,
            window_info={
                "title": "",
                "left": 0,
                "top": 0,
                "width": 0,
                "height": 0,
            },
        )
        escape_pressed = MagicMock()
        dialog.escape_pressed.connect(escape_pressed)

        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Escape,
            Qt.KeyboardModifier.NoModifier,
        )
        dialog.keyPressEvent(event)

        escape_pressed.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
