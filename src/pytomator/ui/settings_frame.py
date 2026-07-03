"""Settings frame - global settings and current project settings."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QGroupBox, QFormLayout
)

from pytomator.config.config_manager import ConfigManager
from pytomator.project.manager import ProjectManager


class SettingsFrame(QWidget):
    def __init__(self, project_manager: ProjectManager):
        super().__init__()

        self.project_manager = project_manager

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # ── Global Settings ──────────────────────────────────
        global_group = QGroupBox("Global Settings")
        global_layout = QFormLayout()
        global_group.setLayout(global_layout)

        self.toggle_run_hotkey_field = QHBoxLayout()
        self.toggle_run_hotkey_field.addWidget(QLabel("Toggle Run Hotkey:"))
        self.toggle_run_hotkey_lineedit = QLineEdit()
        self.toggle_run_hotkey_field.addWidget(self.toggle_run_hotkey_lineedit)
        global_layout.addRow(self.toggle_run_hotkey_field)

        self.capture_hotkey_field = QHBoxLayout()
        self.capture_hotkey_field.addWidget(QLabel("Capture Region Hotkey:"))
        self.capture_hotkey_lineedit = QLineEdit()
        self.capture_hotkey_field.addWidget(self.capture_hotkey_lineedit)
        global_layout.addRow(self.capture_hotkey_field)

        self.layout.addWidget(global_group)

        # ── Project Settings ─────────────────────────────────
        self.project_group = QGroupBox("Project Settings")
        project_layout = QFormLayout()
        self.project_group.setLayout(project_layout)

        self.project_loop_default = QCheckBox("Loop scripts by default")
        project_layout.addRow(self.project_loop_default)

        self.project_auto_save = QCheckBox("Auto-save before running")
        project_layout.addRow(self.project_auto_save)

        self.layout.addWidget(self.project_group)

        # ── Save buttons ────────────────────────────────────
        self.layout.addStretch()

        btn_row = QHBoxLayout()
        self.save_global_btn = QPushButton("Save Global Settings")
        self.save_global_btn.clicked.connect(self._on_save_global)
        btn_row.addWidget(self.save_global_btn)

        self.save_project_btn = QPushButton("Save Project Settings")
        self.save_project_btn.clicked.connect(self._on_save_project)
        btn_row.addWidget(self.save_project_btn)

        self.layout.addLayout(btn_row)

        # ── Bind to config manager ─────────────────────────
        self.config_manager = ConfigManager.get_instance()
        self.config_manager.on("config_applied", self._apply_global_settings)
        self._apply_global_settings(self.config_manager.config)

        # ── Bind to project manager ────────────────────────
        self.project_manager.on("project_loaded", self._on_project_loaded)
        self.project_manager.on("project_closed", self._on_project_closed)
        self._update_project_settings_ui()

    # ------------------------------------------------------------------
    # Global settings
    # ------------------------------------------------------------------

    def _on_save_global(self):
        config = self.config_manager.config.copy()
        hotkeys = config.get("hotkeys", {})
        hotkeys["toggle_script"] = self.toggle_run_hotkey_lineedit.text().strip()
        hotkeys["capture_region"] = self.capture_hotkey_lineedit.text().strip()
        config["hotkeys"] = hotkeys
        self.config_manager.save_config(config)

    def _apply_global_settings(self, config):
        hotkeys = config.get("hotkeys", {})
        self.toggle_run_hotkey_lineedit.setText(hotkeys.get("toggle_script", ""))
        self.capture_hotkey_lineedit.setText(hotkeys.get("capture_region", ""))

    # ------------------------------------------------------------------
    # Project settings
    # ------------------------------------------------------------------

    def _on_project_loaded(self):
        self._update_project_settings_ui()

    def _on_project_closed(self):
        self._update_project_settings_ui()

    def _update_project_settings_ui(self):
        """Load current project settings into the UI."""
        has_project = self.project_manager.is_project_open
        self.project_group.setEnabled(has_project)

        if has_project:
            settings = self.project_manager.get_project_settings()
            if settings:
                self.project_loop_default.setChecked(settings.loop_default)
                self.project_auto_save.setChecked(settings.auto_save)

    def _on_save_project(self):
        """Save project settings from UI back to the model."""
        if not self.project_manager.is_project_open:
            return

        self.project_manager.update_project_settings(
            loop_default=self.project_loop_default.isChecked(),
            auto_save=self.project_auto_save.isChecked(),
        )