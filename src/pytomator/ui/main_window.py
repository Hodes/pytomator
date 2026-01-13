from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout
)
from PyQt6.QtGui import QIcon

from pytomator.ui.editor_frame import EditorFrame
from pytomator.core.script_runner import ScriptRunner

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Hodes Pytomator")
        self.setWindowIcon(QIcon(":/icons/app_64.png"))

        self.script_runner = ScriptRunner()
    
        # Tabs for different views
        tabs = QTabWidget()
        tabs.addTab(self._create_editor_tab(), "Script Editor")
        
        self.setCentralWidget(tabs)
    
    def _create_editor_tab(self) -> QWidget:
        return EditorFrame(self.script_runner)