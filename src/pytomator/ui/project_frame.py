"""Project frame - dashboard tab for creating, opening, and saving .pytom projects."""

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QPushButton, QFileDialog, QInputDialog,
    QMessageBox, QLineEdit, QLabel, QTextEdit, QGroupBox
)
from PyQt6.QtCore import pyqtSignal
import qtawesome as qta

from pytomator.project.manager import ProjectManager
from pytomator.config.config_manager import ConfigManager


class ProjectFrame(QWidget):
    """Tab for managing the current .pytom project."""

    project_opened = pyqtSignal()  # Emitted when a project is loaded or created
    project_closed = pyqtSignal()

    def __init__(self, project_manager: ProjectManager):
        super().__init__()
        self.project_manager = project_manager
        self.config_manager = ConfigManager.get_instance()

        # Listen to manager events to update UI
        self.project_manager.on("project_loaded", self._on_project_loaded)
        self.project_manager.on("project_closed", self._on_project_closed)
        self.project_manager.on("project_saved", self._on_project_saved)

        self._build_ui()
        self._update_ui_state()

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _get_last_dir(self) -> str:
        """Return the last project directory stored in config, or empty string."""
        return self.config_manager.config.get("last_project_dir", "")

    def _get_last_project_path(self) -> Path | None:
        """Return the last project file stored in config, if any."""
        path = self.config_manager.config.get("last_project_path", "")
        return Path(path) if path else None

    def _save_last_project(self, path: Path) -> None:
        """Persist the project file and its directory to config."""
        project_path = path.resolve()
        self.config_manager.config["last_project_path"] = str(project_path)
        self.config_manager.config["last_project_dir"] = str(project_path.parent)
        self.config_manager.save_config(self.config_manager.config)

    def _open_project_file(self, start_dir: str) -> None:
        """Open file dialog and load the selected project."""
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Project", start_dir,
            "Pytomator Project (*.pytom);;All Files (*)"
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            self.project_manager.load_project(path)
            project_path = self.project_manager.project_path
            if project_path:
                self._save_last_project(project_path)
            self._update_ui_state()
            self.project_opened.emit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project:\n{e}")

    # ------------------------------------------------------------------
    # UI Build
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        # ── Action buttons (always visible) ─────────────────────
        actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout()
        actions_group.setLayout(actions_layout)

        # Row 1
        row1 = QHBoxLayout()
        self.new_btn = QPushButton("New Project")
        self.new_btn.setIcon(qta.icon("fa6s.file-circle-plus"))
        self.new_btn.clicked.connect(self._on_new_project)
        row1.addWidget(self.new_btn)

        self.open_btn = QPushButton("Open Project")
        self.open_btn.setIcon(qta.icon("fa6s.folder-open"))
        self.open_btn.clicked.connect(self._on_open_project)
        row1.addWidget(self.open_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.setIcon(qta.icon("fa6s.floppy-disk"))
        self.save_btn.clicked.connect(self._on_save)
        row1.addWidget(self.save_btn)

        self.save_as_btn = QPushButton("Save As...")
        self.save_as_btn.setIcon(qta.icon("fa6s.floppy-disk"))
        self.save_as_btn.clicked.connect(self._on_save_as)
        row1.addWidget(self.save_as_btn)

        actions_layout.addLayout(row1)

        # Row 2
        row2 = QHBoxLayout()
        self.close_btn = QPushButton("Close Project")
        self.close_btn.setIcon(qta.icon("fa6s.xmark"))
        self.close_btn.clicked.connect(self._on_close)
        row2.addWidget(self.close_btn)
        row2.addStretch()
        actions_layout.addLayout(row2)

        layout.addWidget(actions_group)

        # ── Last project quick open ─────────────────────────────
        self.last_project_group = QGroupBox("Last Project")
        last_project_layout = QHBoxLayout()
        self.last_project_group.setLayout(last_project_layout)

        self.last_project_label = QLabel("No recent project")
        self.last_project_label.setStyleSheet("color: #888;")
        last_project_layout.addWidget(self.last_project_label, 1)

        self.reopen_btn = QPushButton("Reopen")
        self.reopen_btn.setIcon(qta.icon("fa6s.rotate-left"))
        self.reopen_btn.clicked.connect(self._on_reopen_last)
        self.reopen_btn.setEnabled(False)
        last_project_layout.addWidget(self.reopen_btn)

        layout.addWidget(self.last_project_group)

        # ── Project info group (hidden when no project) ─────────
        self.info_group = QGroupBox("Project Information")
        info_layout = QFormLayout()
        self.info_group.setLayout(info_layout)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("My Automation")
        info_layout.addRow("Name:", self.name_edit)

        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("What does this project do?")
        self.description_edit.setMaximumHeight(80)
        info_layout.addRow("Description:", self.description_edit)

        self.status_label = QLabel()
        self.status_label.setStyleSheet("font-weight: bold; color: #555;")
        info_layout.addRow(self.status_label)

        layout.addWidget(self.info_group)

        layout.addStretch()

    # ------------------------------------------------------------------
    # UI state
    # ------------------------------------------------------------------

    def _update_ui_state(self):
        """Enable/disable controls and show/hide info based on whether a project is open."""
        has_project = self.project_manager.is_project_open
        project = self.project_manager.project

        self.save_btn.setEnabled(has_project)
        self.save_as_btn.setEnabled(has_project)
        self.close_btn.setEnabled(has_project)
        self.info_group.setVisible(has_project)

        if has_project and project:
            self.name_edit.setText(project.name)
            self.description_edit.setText(project.settings.description)
            path = self.project_manager.project_path
            path_str = str(path) if path else "(not yet saved)"
            self.status_label.setText(
                f"Project: {project.name}  |  Scripts: {len(project.scripts)}  |  {path_str}"
            )
        else:
            self.name_edit.clear()
            self.description_edit.clear()
            self.status_label.setText("No project open")

        # Update last project section
        last_project_path = self._get_last_project_path()
        if last_project_path:
            self.last_project_label.setText(str(last_project_path.resolve()))
            self.reopen_btn.setEnabled(last_project_path.is_file())
        else:
            self.last_project_label.setText("No recent project")
            self.reopen_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_new_project(self):
        name, ok = QInputDialog.getText(
            self, "New Project", "Project name:"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        description, ok = QInputDialog.getText(
            self, "New Project", "Description (optional):"
        )
        description = description.strip() if ok else ""
        self.project_manager.create_project(name, description)
        self._update_ui_state()
        self.project_opened.emit()

    def _on_open_project(self):
        start_dir = self._get_last_dir()
        self._open_project_file(start_dir)

    def _on_reopen_last(self):
        """Quickly reopen the last stored project file."""
        path = self._get_last_project_path()
        if path is None or not path.is_file():
            self._update_ui_state()
            return
        try:
            self.project_manager.load_project(path)
            self._save_last_project(self.project_manager.project_path or path)
            self._update_ui_state()
            self.project_opened.emit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to reopen project:\n{e}")
            self._update_ui_state()

    def _on_save(self):
        # Sync name/description from UI to model before saving
        self._sync_metadata()
        success = self.project_manager.save_project()
        if not success:
            # No path yet → do Save As
            self._on_save_as()
        else:
            # After saving, persist the directory
            path = self.project_manager.project_path
            if path:
                self._save_last_project(path)
            self._update_ui_state()

    def _on_save_as(self):
        self._sync_metadata()
        start_dir = self._get_last_dir()
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", start_dir,
            "Pytomator Project (*.pytom);;All Files (*)"
        )
        if not path_str:
            return
        path = Path(path_str)
        success = self.project_manager.save_project(path)
        if not success:
            QMessageBox.critical(self, "Error", "Failed to save project.")
        else:
            project_path = self.project_manager.project_path
            if project_path:
                self._save_last_project(project_path)
        self._update_ui_state()

    def _on_close(self):
        if self.project_manager.is_project_open:
            reply = QMessageBox.question(
                self, "Close Project",
                "Do you want to save before closing?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self._on_save()
        self.project_manager.close_project()
        self._update_ui_state()
        self.project_closed.emit()

    def _sync_metadata(self):
        """Push name/description from UI fields back to the model."""
        if not self.project_manager.is_project_open:
            return
        project = self.project_manager.project
        project.name = self.name_edit.text().strip() or project.name
        project.settings.description = self.description_edit.toPlainText().strip()

    # ------------------------------------------------------------------
    # Event handlers from manager
    # ------------------------------------------------------------------

    def _on_project_loaded(self):
        self._update_ui_state()

    def _on_project_closed(self):
        self._update_ui_state()

    def _on_project_saved(self):
        self._update_ui_state()
