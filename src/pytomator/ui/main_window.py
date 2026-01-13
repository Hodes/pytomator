from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout,
    QPushButton, QCheckBox
)

from pytomator.editor import CodeEditor
from pytomator.core.script_runner import ScriptRunner
from pytomator.core.hotkey_manager import HotkeyManager


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Hodes Pytomator")

        self.editor = CodeEditor()
        self.loop_checkbox = QCheckBox("Loop script")
        self.run_button = QPushButton("Run")
        self.is_running = False

        layout = QVBoxLayout()
        layout.addWidget(self.editor)
        layout.addWidget(self.loop_checkbox)
        layout.addWidget(self.run_button)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        # Runner
        self.runner = ScriptRunner(
            get_code_callback=self.editor.get_code
        )
        self.runner.on("started", lambda: self.on_runner_state_change(True))
        self.runner.on("finished", lambda: self.on_runner_state_change(False))        

        # Botão
        self.run_button.clicked.connect(self.run_toggle)

        # Hotkey global
        self.hotkeys = HotkeyManager()
        self.hotkeys.register("ctrl+alt+r", self.run_toggle)
        
    def update_run_button(self, is_running: bool):
        if is_running:
            self.run_button.setText("Stop")
        else:
            self.run_button.setText("Run")

    def on_runner_state_change(self, is_running: bool):
        self.update_run_button(is_running)
    
    def run_toggle(self):
        if self.runner._running:
            self.runner.stop()
        else:
            self.runner.start(loop=self.loop_checkbox.isChecked())