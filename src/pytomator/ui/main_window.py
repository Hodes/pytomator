from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget
)
from PyQt6.QtGui import QIcon
import qtawesome as qta

from pytomator.ui.about_frame import AboutFrame
from pytomator.ui.editor_frame import EditorFrame
from pytomator.core.script_runner import ScriptRunner
from pytomator.ui.settings_frame import SettingsFrame

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Hodes Pytomator")
        self.setWindowIcon(QIcon(":/icons/app_64.png"))
        # Window size
        self.resize(600, 800)

        self.script_runner = ScriptRunner()
        self.script_runner.on("started", lambda: self.on_runner_state_change(True))
        self.script_runner.on("finished", lambda: self.on_runner_state_change(False))
        self.script_runner.on("interrupted", lambda: self.on_runner_state_change(False))
    
        # Tabs for different views
        tabs = QTabWidget()
        tabs.addTab(EditorFrame(self.script_runner), "Script Editor")
        tabs.addTab(SettingsFrame(), "Settings")
        tabs.addTab(AboutFrame(), "About")  # Placeholder for AboutFrame
        # Tab icons
        tabs.setTabIcon(0, qta.icon("fa6s.code"))
        tabs.setTabIcon(1, qta.icon("fa5s.cog"))
        tabs.setTabIcon(2, qta.icon("mdi.help-circle"))

        # Status bar
        self.statusBar().showMessage("Ready")
        
        self.setCentralWidget(tabs)

    def on_runner_state_change(self, is_running: bool):
        if is_running:
            self.statusBar().showMessage("Script is running...")
        else:
            self.statusBar().showMessage("Script is stopped.")