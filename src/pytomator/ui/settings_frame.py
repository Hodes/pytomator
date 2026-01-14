
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton
)

from pytomator.config import config_manager
from pytomator.config.config_manager import ConfigManager


class SettingsFrame(QWidget):
    def __init__(self):
        super().__init__()
    
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        # Field toggle run hotkey
        self.toggle_run_hotkey_field = QHBoxLayout()
        self.toggle_run_hotkey_field.addWidget(QLabel("Toggle Run Hotkey:"))
        self.toggle_run_hotkey_lineedit = QLineEdit()
        self.toggle_run_hotkey_field.addWidget(self.toggle_run_hotkey_lineedit)
        self.layout.addLayout(self.toggle_run_hotkey_field)
        
        self.layout.addStretch()
        
        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self.on_save_clicked)
        
        self.layout.addWidget(self.save_button)
        
        # Bind to config manager
        self.config_manager = ConfigManager.get_instance()
        self.config_manager.on("config_applied", self.apply_settings)
        self.apply_settings(self.config_manager.config)
        
    def on_save_clicked(self):
        config = self.config_manager.config.copy()
        hotkeys = config.get("hotkeys", {})
        hotkeys["toggle_script"] = self.toggle_run_hotkey_lineedit.text().strip()
        config["hotkeys"] = hotkeys
        self.config_manager.save_config(config)

    def apply_settings(self, config):
        # Apply settings from the config dictionary to the UI elements
        hotkeys = config.get("hotkeys", {})
        self.toggle_run_hotkey_lineedit.setText(hotkeys.get("toggle_script", ""))