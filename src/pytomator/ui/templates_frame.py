"""Templates management frame - list, preview, edit, and manage captured templates."""

from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QGroupBox,
    QFormLayout, QDoubleSpinBox, QLineEdit, QMessageBox,
    QFrame, QScrollArea, QCheckBox,
)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt, pyqtSignal

from pytomator.core.vision.models import TemplateCapture
from pytomator.core.vision.capture_tool import load_template_image
from pytomator.core.vision.template_matcher import find_on_screen
from pytomator.core.vision.search_context import prepare_search_context
from pytomator.project.manager import ProjectManager
from pytomator.ui.capture.capture_manager import CaptureManager
from pytomator.config import ConfigManager


class TemplatesFrame(QWidget):
    """UI for managing captured templates in the current project."""

    def __init__(self, project_manager: ProjectManager, capture_manager: CaptureManager):
        super().__init__()

        self._project_manager = project_manager
        self._capture_manager = capture_manager
        self._current_template: Optional[TemplateCapture] = None

        self._setup_ui()

        # Connect signals
        self._project_manager.on("project_loaded", self._on_project_changed)
        self._project_manager.on("project_closed", self._on_project_changed)
        self._project_manager.on("project_saved", self._update_capture_button_state)
        self._capture_manager.template_saved.connect(self._on_template_saved)

        # Listen for config changes to update hotkey label
        ConfigManager.get_instance().on("config_applied", self._update_capture_button_text)

        # Initial state: disabled until a project is loaded
        self._update_capture_button_state()

    def _setup_ui(self):
        main_layout = QHBoxLayout()
        self.setLayout(main_layout)

        # ── Splitter: list on left, details on right ────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: template list
        left_widget = QWidget()
        left_layout = QVBoxLayout()
        left_widget.setLayout(left_layout)

        list_header = QHBoxLayout()
        list_header.addWidget(QLabel("<b>Templates</b>"))
        self._capture_btn = QPushButton()
        self._capture_btn.clicked.connect(self._on_capture_new)
        list_header.addWidget(self._capture_btn)
        left_layout.addLayout(list_header)

        self._template_list = QListWidget()
        self._template_list.setMinimumWidth(200)
        self._template_list.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._template_list)

        splitter.addWidget(left_widget)

        # Right: details panel
        right_widget = QScrollArea()
        right_widget.setWidgetResizable(True)
        self._details_panel = QWidget()
        self._details_layout = QVBoxLayout()
        self._details_panel.setLayout(self._details_layout)
        right_widget.setWidget(self._details_panel)
        splitter.addWidget(right_widget)

        splitter.setSizes([250, 500])

        main_layout.addWidget(splitter)

        # Set initial button text with hotkey
        self._update_capture_button_text()

        # Build details panel (initially empty state)
        self._build_details_panel()

    def _build_details_panel(self):
        """Build or rebuild the details panel."""
        # Clear existing
        while self._details_layout.count():
            item = self._details_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._current_template is None:
            # Empty state
            empty_label = QLabel("Select a template from the list\nto view its details.")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
            self._details_layout.addWidget(empty_label)
            return

        t = self._current_template

        # ── Preview ──────────────────────────────────────────
        preview_group = QGroupBox("Preview")
        preview_layout = QVBoxLayout()
        preview_group.setLayout(preview_layout)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumHeight(150)
        self._load_preview_image()
        preview_layout.addWidget(self._preview_label)

        self._details_layout.addWidget(preview_group)

        # ── Editable fields ──────────────────────────────────
        edit_group = QGroupBox("Properties")
        edit_layout = QFormLayout()
        edit_group.setLayout(edit_layout)

        # Name
        self._name_edit = QLineEdit(t.name)
        self._name_edit.textChanged.connect(self._on_name_changed)
        edit_layout.addRow("Name:", self._name_edit)

        # Confidence
        self._confidence_spin = QDoubleSpinBox()
        self._confidence_spin.setRange(0.0, 1.0)
        self._confidence_spin.setSingleStep(0.05)
        self._confidence_spin.setDecimals(2)
        self._confidence_spin.setValue(t.confidence)
        self._confidence_spin.valueChanged.connect(self._on_confidence_changed)
        edit_layout.addRow("Confidence:", self._confidence_spin)

        self._autofocus_check = QCheckBox("Enable autofocus")
        self._autofocus_check.setChecked(t.autofocus)
        self._autofocus_check.toggled.connect(self._on_autofocus_toggled)
        edit_layout.addRow("Window focus:", self._autofocus_check)

        self._multi_scale_check = QCheckBox("Enable multi-scale matching")
        self._multi_scale_check.setChecked(t.multi_scale_enabled)
        self._multi_scale_check.toggled.connect(self._on_multi_scale_toggled)
        edit_layout.addRow("Scale matching:", self._multi_scale_check)

        self._min_scale_spin = QDoubleSpinBox()
        self._min_scale_spin.setRange(0.1, t.max_scale)
        self._min_scale_spin.setSingleStep(0.1)
        self._min_scale_spin.setDecimals(2)
        self._min_scale_spin.setValue(t.min_scale)
        self._min_scale_spin.valueChanged.connect(self._on_min_scale_changed)
        edit_layout.addRow("Minimum scale:", self._min_scale_spin)

        self._max_scale_spin = QDoubleSpinBox()
        self._max_scale_spin.setRange(t.min_scale, 5.0)
        self._max_scale_spin.setSingleStep(0.1)
        self._max_scale_spin.setDecimals(2)
        self._max_scale_spin.setValue(t.max_scale)
        self._max_scale_spin.valueChanged.connect(self._on_max_scale_changed)
        edit_layout.addRow("Maximum scale:", self._max_scale_spin)
        self._set_scale_controls_enabled(t.multi_scale_enabled)

        self._details_layout.addWidget(edit_group)

        # ── Metadata (read-only) ─────────────────────────────
        meta_group = QGroupBox("Capture Metadata")
        meta_layout = QFormLayout()
        meta_group.setLayout(meta_layout)

        meta_layout.addRow("ID:", QLabel(t.id))
        meta_layout.addRow("Absolute:", QLabel(f"({t.region_abs[0]}, {t.region_abs[1]}, {t.region_abs[2]}, {t.region_abs[3]})"))
        meta_layout.addRow("Relative:", QLabel(f"({t.region_rel[0]}, {t.region_rel[1]}, {t.region_rel[2]}, {t.region_rel[3]})"))
        meta_layout.addRow("Resolution:", QLabel(f"{t.screen_width} × {t.screen_height}"))
        meta_layout.addRow("Abs %:", QLabel(f"({t.pct_abs[0]}%, {t.pct_abs[1]}%, {t.pct_abs[2]}%, {t.pct_abs[3]}%)"))
        meta_layout.addRow("Rel %:", QLabel(f"({t.pct_rel[0]}%, {t.pct_rel[1]}%, {t.pct_rel[2]}%, {t.pct_rel[3]}%)"))
        meta_layout.addRow("Window:", QLabel(t.active_window_title or "(none)"))
        meta_layout.addRow("Created:", QLabel(t.created_at.strftime("%Y-%m-%d %H:%M:%S")))

        self._details_layout.addWidget(meta_group)

        # ── Action buttons ───────────────────────────────────
        actions_group = QGroupBox("Actions")
        actions_layout = QHBoxLayout()
        actions_group.setLayout(actions_layout)

        locate_btn = QPushButton("Locate on Screen")
        locate_btn.clicked.connect(self._on_locate)
        actions_layout.addWidget(locate_btn)

        recapture_btn = QPushButton("Recapture")
        recapture_btn.clicked.connect(self._on_recapture)
        actions_layout.addWidget(recapture_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setStyleSheet("color: red;")
        delete_btn.clicked.connect(self._on_delete)
        actions_layout.addWidget(delete_btn)

        self._details_layout.addWidget(actions_group)

        self._details_layout.addStretch()

    def _load_preview_image(self):
        """Load and display the template preview image."""
        if not self._current_template or not self._project_manager.project_path:
            return

        image = load_template_image(
            self._project_manager.project_path,
            self._current_template.image_path,
        )
        if image:
            from PIL.ImageQt import ImageQt
            qimage = ImageQt(image)
            pixmap = QPixmap.fromImage(qimage)
            scaled = pixmap.scaled(
                400, 200,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._preview_label.setPixmap(scaled)

    def _refresh_list(self):
        """Refresh the template list from the project data."""
        self._template_list.blockSignals(True)
        self._template_list.clear()

        if self._project_manager.is_project_open and self._project_manager.project:
            for t in self._project_manager.project.templates:
                item = QListWidgetItem(t.name)
                item.setData(Qt.ItemDataRole.UserRole, t.id)
                self._template_list.addItem(item)

        self._template_list.blockSignals(False)

    def _update_capture_button_text(self, config=None):
        """Update the capture button text to show the configured hotkey."""
        if config is None:
            config = ConfigManager.get_instance().config
        hotkey = config.get("hotkeys", {}).get("capture_region", "ctrl+shift+f7")
        # Display the hotkey in a user-friendly way: uppercase, no shift prefix redundancy
        display = hotkey.replace("ctrl", "Ctrl").replace("shift", "Shift").replace("alt", "Alt").replace("+", "+")
        self._capture_btn.setText(f"Capture New ({display})")

    def _update_capture_button_state(self):
        """Enable or disable the capture button based on project state."""
        has_project = self._project_manager.is_project_open and self._project_manager.project_path is not None
        self._capture_btn.setEnabled(has_project)
        self._update_capture_button_text()

    def _on_project_changed(self):
        """Called when the project is loaded or closed."""
        self._current_template = None
        self._refresh_list()
        self._build_details_panel()
        self._update_capture_button_state()

    def _on_template_saved(self, template: TemplateCapture):
        """Called when a new template is saved via CaptureManager."""
        self._refresh_list()
        # Select the newly added template
        for i in range(self._template_list.count()):
            item = self._template_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == template.id:
                self._template_list.setCurrentItem(item)
                break

    def _on_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Called when the user selects a different template in the list."""
        if current is None:
            self._current_template = None
            self._build_details_panel()
            return

        template_id = current.data(Qt.ItemDataRole.UserRole)
        if self._project_manager.project:
            for t in self._project_manager.project.templates:
                if t.id == template_id:
                    self._current_template = t
                    self._build_details_panel()
                    return

        self._current_template = None
        self._build_details_panel()

    def _on_capture_new(self):
        """Start a new capture."""
        self._capture_manager.start_capture()

    def _on_name_changed(self, new_name: str):
        """Update the template name in the project."""
        if not self._current_template or not self._project_manager.project:
            return
        self._current_template.name = new_name
        self._project_manager.project.updated_at = __import__("datetime").datetime.now()
        self._project_manager.save_project()
        # Update list item
        self._refresh_list()

    def _on_confidence_changed(self, value: float):
        """Update the confidence value in the project."""
        if not self._current_template or not self._project_manager.project:
            return
        self._current_template.confidence = value
        self._project_manager.project.updated_at = __import__("datetime").datetime.now()
        self._project_manager.save_project()

    def _set_scale_controls_enabled(self, enabled: bool):
        self._min_scale_spin.setEnabled(enabled)
        self._max_scale_spin.setEnabled(enabled)

    def _save_template_properties(self):
        if not self._current_template or not self._project_manager.project:
            return
        self._project_manager.project.updated_at = __import__("datetime").datetime.now()
        self._project_manager.save_project()

    def _on_multi_scale_toggled(self, enabled: bool):
        if not self._current_template:
            return
        self._current_template.multi_scale_enabled = enabled
        self._set_scale_controls_enabled(enabled)
        self._save_template_properties()

    def _on_autofocus_toggled(self, enabled: bool):
        if not self._current_template:
            return
        self._current_template.autofocus = enabled
        self._save_template_properties()

    def _on_min_scale_changed(self, value: float):
        if not self._current_template:
            return
        self._current_template.min_scale = value
        self._max_scale_spin.setMinimum(value)
        self._save_template_properties()

    def _on_max_scale_changed(self, value: float):
        if not self._current_template:
            return
        self._current_template.max_scale = value
        self._min_scale_spin.setMaximum(value)
        self._save_template_properties()

    def _on_locate(self):
        """Test template matching on the current screen."""
        if not self._current_template or not self._project_manager.project_path:
            return

        context = prepare_search_context(
            self._current_template,
            autofocus=None,
        )
        result = None if context is None else find_on_screen(
            self._current_template,
            self._project_manager.project_path,
            search_region=context.region,
            debug=bool(
                self._project_manager.project
                and self._project_manager.project.settings.vision_debug
            ),
            window_info=context.window,
        )

        if result:
            x, y, w, h = result
            QMessageBox.information(
                self,
                "Template Found",
                f"Template '{self._current_template.name}' found at:\n"
                f"Position: ({x}, {y})\n"
                f"Size: {w} × {h}\n"
                f"Confidence: {self._current_template.confidence:.2f}",
            )
        else:
            QMessageBox.warning(
                self,
                "Template Not Found",
                f"Template '{self._current_template.name}' was not found on the screen.\n"
                f"Try lowering the confidence threshold or recapturing.",
            )

    def _on_recapture(self):
        """Recapture the same region."""
        if not self._current_template:
            return
        # We could implement recapture of the same region
        # For now, just start a new capture
        self._capture_manager.start_capture()

    def _on_delete(self):
        """Delete the selected template."""
        if not self._current_template or not self._project_manager.project:
            return

        reply = QMessageBox.question(
            self,
            "Delete Template",
            f"Are you sure you want to delete template '{self._current_template.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Remove from project
            self._project_manager.project.templates.remove(self._current_template)
            self._project_manager.project.updated_at = __import__("datetime").datetime.now()
            self._project_manager.save_project()

            # Delete image file
            if self._project_manager.project_path:
                image_path = self._project_manager.project_path / self._current_template.image_path
                if image_path.exists():
                    image_path.unlink()

            self._current_template = None
            self._refresh_list()
            self._build_details_panel()
