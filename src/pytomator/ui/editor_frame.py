"""Editor frame - script editor that operates within the context of a .pytom project."""

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QCheckBox, QLineEdit,
    QMessageBox, QLabel, QComboBox,
    QInputDialog, QFileDialog
)
from PyQt6.QtCore import pyqtSignal
import qtawesome as qta

from pytomator.ui.widgets import CodeEditor
from pytomator.core.hotkey_manager import HotkeyManager
from pytomator.config import ConfigManager
from pytomator.project.manager import ProjectManager


class EditorFrame(QWidget):

    script_error_signal = pyqtSignal(str)
    _run_script_hotkey_signal = pyqtSignal(str)  # Emitted from hotkey thread, handled on main thread
    _toggle_script_signal = pyqtSignal()          # Thread-safe toggle for global hotkey

    def __init__(self, script_runner, project_manager: ProjectManager):
        super().__init__()

        self.project_manager = project_manager
        self.current_script_name = None  # Name of the script currently in the editor

        # ── Script selector ─────────────────────────────────────
        selector_layout = QHBoxLayout()
        self.script_selector = QComboBox()
        self.script_selector.setMinimumWidth(200)
        self.script_selector.currentTextChanged.connect(self._on_script_selected)
        selector_layout.addWidget(QLabel("Script:"))
        selector_layout.addWidget(self.script_selector)

        self.new_script_btn = QPushButton()
        self.new_script_btn.setIcon(qta.icon("fa6s.plus"))
        self.new_script_btn.setToolTip("New Script")
        self.new_script_btn.clicked.connect(self._on_new_script)
        selector_layout.addWidget(self.new_script_btn)

        self.rename_script_btn = QPushButton()
        self.rename_script_btn.setIcon(qta.icon("fa6s.pencil"))
        self.rename_script_btn.setToolTip("Rename Script")
        self.rename_script_btn.clicked.connect(self._on_rename_script)
        selector_layout.addWidget(self.rename_script_btn)

        self.delete_script_btn = QPushButton()
        self.delete_script_btn.setIcon(qta.icon("fa6s.trash-can"))
        self.delete_script_btn.setToolTip("Delete Script")
        self.delete_script_btn.clicked.connect(self._on_delete_script)
        selector_layout.addWidget(self.delete_script_btn)

        selector_layout.addStretch()

        # ── Editor ──────────────────────────────────────────────
        self.editor = CodeEditor()

        # ── Action buttons ──────────────────────────────────────
        action_buttons_layout = QHBoxLayout()
        self.save_script_btn = QPushButton("Save Script")
        self.save_script_btn.setIcon(qta.icon("fa6s.floppy-disk"))
        self.save_script_btn.clicked.connect(self._on_save_script)
        action_buttons_layout.addWidget(self.save_script_btn)
        action_buttons_layout.addStretch()

        # ── Error status ────────────────────────────────────────
        self.error_status = QLabel()

        # ── Run controls ────────────────────────────────────────
        self.loop_checkbox = QCheckBox("Loop script")
        self.loop_checkbox.toggled.connect(self._on_loop_toggled)

        # ── Hotkey per script ───────────────────────────────────
        hotkey_layout = QHBoxLayout()
        hotkey_layout.addWidget(QLabel("Script hotkey:"))
        self.hotkey_input = QLineEdit()
        self.hotkey_input.setPlaceholderText("e.g. ctrl+shift+f6")
        self.hotkey_input.setToolTip("Enter a hotkey combination for this script")
        hotkey_layout.addWidget(self.hotkey_input)
        self.set_hotkey_btn = QPushButton("Set")
        self.set_hotkey_btn.setIcon(qta.icon("fa6s.check"))
        self.set_hotkey_btn.clicked.connect(self._on_set_hotkey)
        hotkey_layout.addWidget(self.set_hotkey_btn)
        self.clear_hotkey_btn = QPushButton("Clear")
        self.clear_hotkey_btn.setIcon(qta.icon("fa6s.xmark"))
        self.clear_hotkey_btn.clicked.connect(self._on_clear_hotkey)
        hotkey_layout.addWidget(self.clear_hotkey_btn)
        hotkey_layout.addStretch()

        self.run_button = QPushButton("Run")
        self.is_running = False

        # ── Layout assembly ─────────────────────────────────────
        layout = QVBoxLayout()
        layout.addLayout(selector_layout)
        layout.addLayout(action_buttons_layout)
        layout.addWidget(self.editor)
        layout.addWidget(self.error_status)
        layout.addWidget(self.loop_checkbox)
        layout.addLayout(hotkey_layout)
        layout.addWidget(self.run_button)
        self.setLayout(layout)

        # ── Runner ──────────────────────────────────────────────
        self.runner = script_runner

        self.runner.on("started", lambda: self.on_runner_state_change(True))
        self.runner.on("finished", lambda: self.on_runner_state_change(False))
        self.runner.on("interrupted", lambda: self.on_runner_state_change(False))
        self.runner.on("line_executing", self.editor.highlight_line)
        self.runner.on("error", self.update_script_error)

        self.update_run_button(False)
        self.run_button.clicked.connect(self.run_toggle)

        # ── Hotkey global ───────────────────────────────────────
        self.hotkeys = HotkeyManager()
        config_manager = ConfigManager.get_instance()
        config_manager.on("config_applied", self.on_config_applied)
        self.on_config_applied(config_manager.config)

        # ── Thread-safe hotkey signals ──────────────────────────
        self._run_script_hotkey_signal.connect(self._on_run_script_hotkey)
        self._toggle_script_signal.connect(self.run_toggle)

        # ── Other signals ───────────────────────────────────────
        self.script_error_signal.connect(self._on_script_error_update)
        self.update_script_error()

        # ── Project manager events ──────────────────────────────
        self.project_manager.on("project_loaded", self._on_project_changed)
        self.project_manager.on("project_closed", self._on_project_changed)
        self.project_manager.on("script_added", self._on_project_changed)
        self.project_manager.on("script_removed", self._on_project_changed)
        self.project_manager.on("script_renamed", self._on_project_changed)
        self.project_manager.on("active_script_changed", self._on_active_script_changed)
        self.project_manager.on("script_hotkey_changed", self._on_script_hotkey_changed)

        self._refresh_script_list()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_code(self) -> str:
        return self.editor.get_code()

    # ------------------------------------------------------------------
    # Script list management
    # ------------------------------------------------------------------

    def _refresh_script_list(self):
        """Rebuild the script selector combo box from the current project."""
        current = self.script_selector.currentText()
        self.script_selector.blockSignals(True)
        self.script_selector.clear()

        if self.project_manager.is_project_open:
            for script in self.project_manager.list_scripts():
                self.script_selector.addItem(script.name)

            # Restore selection
            active = self.project_manager.get_active_script()
            if active:
                idx = self.script_selector.findText(active.name)
                if idx >= 0:
                    self.script_selector.setCurrentIndex(idx)
            elif current and self.script_selector.findText(current) >= 0:
                self.script_selector.setCurrentText(current)

        self.script_selector.blockSignals(False)
        self._update_editor_state()

    def _update_editor_state(self):
        """Enable/disable editor controls based on whether a script is selected."""
        has_script = self.script_selector.count() > 0 and self.project_manager.is_project_open
        self.editor.setEnabled(has_script)
        self.save_script_btn.setEnabled(has_script)
        self.rename_script_btn.setEnabled(has_script)
        self.delete_script_btn.setEnabled(has_script)
        self.run_button.setEnabled(has_script)
        self.loop_checkbox.setEnabled(has_script)
        self.hotkey_input.setEnabled(has_script)
        self.set_hotkey_btn.setEnabled(has_script)
        self.clear_hotkey_btn.setEnabled(has_script)

        if has_script:
            script_name = self.script_selector.currentText()
            script = self.project_manager.get_script(script_name)
            if script:
                self.editor.setText(script.code)
                self.current_script_name = script_name
                self._load_script_properties(script)
        else:
            self.editor.clear()
            self.current_script_name = None
            self.loop_checkbox.setChecked(False)
            self.hotkey_input.clear()

    def _load_script_properties(self, script):
        """Load loop and hotkey from a script into the UI controls."""
        self.loop_checkbox.blockSignals(True)
        self.loop_checkbox.setChecked(script.loop)
        self.loop_checkbox.blockSignals(False)

        self.hotkey_input.setText(script.hotkey or "")

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_script_selected(self, name: str):
        """When user picks a different script from the combo box."""
        if not name or not self.project_manager.is_project_open:
            return
        # Save current code before switching
        self._save_current_code()
        # Switch active script
        self.project_manager.set_active_script(name)
        # The _on_active_script_changed callback will load the code

    def _on_new_script(self):
        """Create a new script in the current project."""
        if not self.project_manager.is_project_open:
            QMessageBox.warning(self, "No Project", "Please open or create a project first.")
            return

        name, ok = QInputDialog.getText(
            self, "New Script", "Script name:",
            text="script"
        )
        if not ok or not name.strip():
            return

        name = name.strip()
        script = self.project_manager.add_script(name)
        if script is None:
            QMessageBox.warning(self, "Error", f"Could not create script '{name}'. It may already exist.")
            return

        # Select the new script
        self.project_manager.set_active_script(name)

    def _on_rename_script(self):
        """Rename the currently selected script."""
        old_name = self.script_selector.currentText()
        if not old_name:
            return

        new_name, ok = QInputDialog.getText(
            self, "Rename Script", "New name:",
            text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return

        if not self.project_manager.rename_script(old_name, new_name.strip()):
            QMessageBox.warning(self, "Error", f"Could not rename script. Name '{new_name.strip()}' may already exist.")

    def _on_delete_script(self):
        """Delete the currently selected script."""
        name = self.script_selector.currentText()
        if not name:
            return

        reply = QMessageBox.question(
            self, "Delete Script",
            f"Are you sure you want to delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.project_manager.remove_script(name)

    def _on_save_script(self):
        """Save the current script code and persist the project to disk."""
        self._save_current_code()
        # Also save the .pytom project file
        if self.project_manager.is_project_open:
            success = self.project_manager.save_project()
            if not success:
                # No path yet → open Save As dialog
                path_str, _ = QFileDialog.getSaveFileName(
                    self, "Save Project As", "",
                    "Pytomator Project (*.pytom);;All Files (*)"
                )
                if path_str:
                    self.project_manager.save_project(Path(path_str))

    def _save_current_code(self):
        """Persist the current editor content into the project model."""
        if not self.current_script_name or not self.project_manager.is_project_open:
            return
        code = self.editor.get_code()
        self.project_manager.update_script_code(self.current_script_name, code)

    # ------------------------------------------------------------------
    # Loop checkbox
    # ------------------------------------------------------------------

    def _on_loop_toggled(self, checked: bool):
        """Persist loop state immediately when toggled."""
        if not self.current_script_name or not self.project_manager.is_project_open:
            return
        self.project_manager.update_script_loop(self.current_script_name, checked)

    # ------------------------------------------------------------------
    # Hotkey per script
    # ------------------------------------------------------------------

    def _on_set_hotkey(self):
        """Set or change the hotkey for the current script."""
        if not self.current_script_name or not self.project_manager.is_project_open:
            return

        hotkey = self.hotkey_input.text().strip().lower()
        if not hotkey:
            QMessageBox.warning(self, "Invalid Hotkey", "Please enter a hotkey combination.")
            return

        # Validate against other project scripts
        is_valid, message = self.project_manager.validate_hotkey(hotkey, exclude_script=self.current_script_name)
        if not is_valid:
            # Conflict found - ask if user wants to replace
            reply = QMessageBox.question(
                self, "Hotkey Conflict",
                f"{message}\n\nDo you want to reassign this hotkey to the current script?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            # Find the conflicting script and clear its hotkey
            for script in self.project_manager.list_scripts():
                if script.name != self.current_script_name and script.hotkey and script.hotkey.lower() == hotkey:
                    self.project_manager.update_script_hotkey(script.name, None)
                    break

        # Set the hotkey
        self.project_manager.update_script_hotkey(self.current_script_name, hotkey)
        # _on_script_hotkey_changed will reinstall all hotkeys

    def _on_clear_hotkey(self):
        """Clear the hotkey for the current script."""
        if not self.current_script_name or not self.project_manager.is_project_open:
            return
        self.project_manager.update_script_hotkey(self.current_script_name, None)
        self.hotkey_input.clear()

    # ------------------------------------------------------------------
    # Project change handlers
    # ------------------------------------------------------------------

    def _on_project_changed(self, *args):
        """Refresh the entire script list when the project changes."""
        self._refresh_script_list()
        self._install_all_hotkeys()

    def _on_active_script_changed(self, name: str):
        """Load the newly active script into the editor."""
        if not name:
            return
        script = self.project_manager.get_script(name)
        if script:
            # Block signals to avoid recursive selection
            self.script_selector.blockSignals(True)
            idx = self.script_selector.findText(name)
            if idx >= 0:
                self.script_selector.setCurrentIndex(idx)
            self.script_selector.blockSignals(False)

            self.editor.setText(script.code)
            self.current_script_name = name
            self._load_script_properties(script)

    def _on_script_hotkey_changed(self, name: str, hotkey: str):
        """Reinstall all hotkeys when any script's hotkey changes."""
        self._install_all_hotkeys()

    # ------------------------------------------------------------------
    # Hotkey installation
    # ------------------------------------------------------------------

    def _install_all_hotkeys(self):
        """Clear and re-register all hotkeys (global + per-script)."""
        self.hotkeys.clear_all()

        # 1. Global toggle hotkey from config
        config_manager = ConfigManager.get_instance()
        hotkey_cfg = config_manager.config.get("hotkeys", {})
        toggle_script_key = hotkey_cfg.get("toggle_script", "F10")
        try:
            self.hotkeys.register("toggle_script", toggle_script_key.lower(), self._toggle_script_signal.emit)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to register global hotkey '{toggle_script_key}':\n{e}")

        # 2. Per-script hotkeys
        if self.project_manager.is_project_open:
            for script in self.project_manager.list_scripts():
                if script.hotkey:
                    try:
                        self.hotkeys.register(
                            f"script_{script.name}",
                            script.hotkey.lower(),
                            self._make_script_callback(script.name)
                        )
                    except Exception as e:
                        QMessageBox.critical(
                            self, "Error",
                            f"Failed to register hotkey '{script.hotkey}' for script '{script.name}':\n{e}"
                        )

    def _make_script_callback(self, script_name: str):
        """Create a callback that emits a signal to run a script on the main thread."""
        def callback():
            self._run_script_hotkey_signal.emit(script_name)
        return callback

    def _on_run_script_hotkey(self, script_name: str):
        """Handle hotkey-triggered script execution on the main thread."""
        if not script_name or not self.project_manager.is_project_open:
            return
        # Save current code first
        self._save_current_code()
        # Switch to the target script
        self.project_manager.set_active_script(script_name)
        # Run it
        self.run_toggle()

    # ------------------------------------------------------------------
    # Config / Hotkeys
    # ------------------------------------------------------------------

    def on_config_applied(self, config):
        """Called when global config is applied. Reinstall all hotkeys."""
        self._install_all_hotkeys()

    # ------------------------------------------------------------------
    # Run controls
    # ------------------------------------------------------------------

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
            # Auto-save before running
            if self.project_manager.is_project_open and self.project_manager.project.settings.auto_save:
                self._save_current_code()
                # Persist project file only if it was already saved somewhere
                if self.project_manager.project_path is not None:
                    self.project_manager.save_project()

            code = self.get_code()
            self.runner.start(code, loop=self.loop_checkbox.isChecked())

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