
from PyQt6.QtWidgets import (
    QFrame, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QCheckBox, QFileDialog,
    QMessageBox, QLineEdit
)

from pytomator.editor import CodeEditor
from pytomator.core.script_runner import ScriptRunner
from pytomator.core.hotkey_manager import HotkeyManager

class EditorFrame(QWidget):
    def __init__(self, script_runner):
        super().__init__()
        
        self.current_script_path = QLineEdit()
        self.load_button = QPushButton("Load Script")
        self.save_button = QPushButton("Save Script")
        self.editor = CodeEditor()
        self.loop_checkbox = QCheckBox("Loop script")
        self.run_button = QPushButton("Run")
        self.is_running = False
        
        fileLayout = QHBoxLayout()
        fileLayout.addWidget(self.current_script_path)
        fileLayout.addWidget(self.load_button)
        
        actionButtonsLayout = QHBoxLayout()
        actionButtonsLayout.addWidget(self.save_button)
        actionButtonsLayout.addStretch()

        layout = QVBoxLayout()
        layout.addLayout(fileLayout)
        layout.addLayout(actionButtonsLayout)
        layout.addWidget(self.editor)
        layout.addWidget(self.loop_checkbox)
        layout.addWidget(self.run_button)

        self.setLayout(layout)
        
        # File Handling
        self.load_button.clicked.connect(self.on_click_load_script)
        self.save_button.clicked.connect(self.on_click_save_script)

        # Runner
        self.runner = script_runner
        self.runner.set_get_code_callback(self.get_code)
        self.runner.on("started", lambda: self.on_runner_state_change(True))
        self.runner.on("finished", lambda: self.on_runner_state_change(False))
        self.runner.on("interrupted", lambda: self.on_runner_state_change(False))

        # Botão
        self.run_button.clicked.connect(self.run_toggle)

        # Hotkey global
        self.hotkeys = HotkeyManager()
        self.hotkeys.register("f10", self.run_toggle)

    def get_code(self) -> str:
        return self.editor.get_code()

    def on_click_load_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Script", "", "Python Files (*.py);;All Files (*)"
        )
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as file:
                    code = file.read()
                self.editor.setText(code)
                self.current_script_path.setText(path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load script:\n{e}")
    
    def on_click_save_script(self):
        path = self.current_script_path.text()
        if not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Script", "", "Python Files (*.py);;All Files (*)"
            )
            if not path:
                return
            self.current_script_path.setText(path)
        try:
            with open(path, 'w', encoding='utf-8') as file:
                file.write(self.editor.get_code())
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save script:\n{e}")
    
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