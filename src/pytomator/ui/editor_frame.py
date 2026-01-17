
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QCheckBox, QFileDialog,
    QMessageBox, QLineEdit, QLabel, QStyle
)
from PyQt6.QtCore import pyqtSignal
import qtawesome as qta

from pytomator.ui.widgets import CodeEditor
from pytomator.core.hotkey_manager import HotkeyManager
from pytomator.config import ConfigManager

class EditorFrame(QWidget):
    
    script_error_signal = pyqtSignal(str)
    
    def __init__(self, script_runner):
        super().__init__()
        
        self.current_script_path = QLineEdit()
        self.load_button = QPushButton("Load Script")
        self.save_button = QPushButton("Save Script")
        self.editor = CodeEditor()
        self.loop_checkbox = QCheckBox("Loop script")
        self.run_button = QPushButton("Run")
        self.error_status = QLabel()
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
        layout.addWidget(self.error_status)
        layout.addWidget(self.loop_checkbox)
        layout.addWidget(self.run_button)

        self.setLayout(layout)
        
        # File Handling
        self.load_button.clicked.connect(self.on_click_load_script)
        self.save_button.clicked.connect(self.on_click_save_script)

        # Runner
        self.runner = script_runner
        
        self.runner.on("started", lambda: self.on_runner_state_change(True))
        self.runner.on("finished", lambda: self.on_runner_state_change(False))
        self.runner.on("interrupted", lambda: self.on_runner_state_change(False))
        self.runner.on("line_executing", self.editor.highlight_line)
        self.runner.on("error", self.update_script_error)

        # Botão
        self.update_run_button(False)
        self.run_button.clicked.connect(self.run_toggle)

        # Hotkey global
        self.hotkeys = HotkeyManager()
        config_manager = ConfigManager.get_instance()
        config_manager.on("config_applied", self.on_config_applied)
        self.on_config_applied(config_manager.config)
        
        # Other signals
        self.script_error_signal.connect(self._on_script_error_update)
        self.update_script_error()

    def get_code(self) -> str:
        return self.editor.get_code()
    
    def on_config_applied(self, config):
        hotkeys = config.get("hotkeys", {})
        toggle_script_key = hotkeys.get("toggle_script", "F10")
        try:
            self.hotkeys.register("toggle_script", toggle_script_key.lower(), self.run_toggle)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to register hotkey '{toggle_script_key}':\n{e}")

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
            self.run_button.setIcon(qta.icon("fa6s.stop"))
            self.run_button.setToolTip("Stop script execution")
        else:
            self.run_button.setText("Run")
            self.run_button.setIcon(qta.icon("fa6s.play"))
            self.run_button.setToolTip("Run script")

    def on_runner_state_change(self, is_running: bool):
        self.update_run_button(is_running)
        if not is_running:
            self.editor.clearExecutionMarker()
    
    def run_toggle(self):
        self.update_script_error()
        if self.runner._running:
            self.runner.stop()
        else:
            self.runner.start(self.get_code(), loop=self.loop_checkbox.isChecked())
            
    def update_script_error(self, error: str = ''):
        self.script_error_signal.emit(error)
    
    def _on_script_error_update(self, error: str):
        if not error.strip():
            self.error_status.setText('Ok')
            self.error_status.setStyleSheet("""
                QLabel {
                    padding: 8px;
                    color: #2356FF;
                    background-color: #C7E1F7;
                    border-left: 3px solid #0077E6;
                }
            """)
        else:
            self.error_status.setText(error)
            self.error_status.setStyleSheet("""
                QLabel {
                    padding: 8px;
                    color: #B92222;
                    background-color: #F3CCC5;
                    border-left: 3px solid #ff0000;
                }
            """)