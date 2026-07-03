import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from pytomator.ui.widgets.code_editor import (
    CodeEditor,
    _DARK_THEME,
    _LIGHT_THEME,
)


class CodeEditorThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_theme_follows_qt_window_palette(self):
        light = QPalette()
        light.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
        dark = QPalette()
        dark.setColor(QPalette.ColorRole.Window, QColor("#202124"))

        self.assertIs(CodeEditor._theme_for_palette(light), _LIGHT_THEME)
        self.assertIs(CodeEditor._theme_for_palette(dark), _DARK_THEME)

    def test_editor_handles_tracking_for_empty_long_and_unicode_lines(self):
        editor = CodeEditor()
        self.addCleanup(editor.close)
        editor.setText("\n" + ("x" * 1000) + "\nmensagem = 'Olá, 世界'")

        for line in (1, 2, 3):
            editor.highlight_line(line)
            self.assertNotEqual(
                editor.markersAtLine(line - 1) & (1 << editor.EXECUTION_MARKER),
                0,
            )

        editor.clearExecutionMarker()
        for line in range(editor.lines()):
            self.assertEqual(
                editor.markersAtLine(line) & (1 << editor.EXECUTION_MARKER),
                0,
            )


if __name__ == "__main__":
    unittest.main()
