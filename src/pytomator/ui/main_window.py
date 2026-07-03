"""Main window - orchestrates project management, script editing, and settings."""

from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QLabel
)
from PyQt6.QtGui import QIcon, QColor, QGuiApplication
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSettings
import qtawesome as qta

from pytomator.ui.about_frame import AboutFrame
from pytomator.ui.editor_frame import EditorFrame
from pytomator.ui.project_frame import ProjectFrame
from pytomator.core.script_runner import ScriptRunner
from pytomator.ui.settings_frame import SettingsFrame
from pytomator.ui.templates_frame import TemplatesFrame
from pytomator.ui.capture.capture_manager import CaptureManager
from pytomator.project.manager import ProjectManager
from pytomator.core.automator import api as automator_api


APP_STATES = {
    "stopped": {
        "title": "Stopped",
        "icon": "fa6.circle-stop",
        "color": QColor("#f84545"),
        "animation": False,
        "bgcolor": "#fcb6b6",
        "border": "#ff0000"
    },
    "running": {
        "title": "Running",
        "icon": "fa6s.spinner",
        "color": QColor("#26a81a"),
        "animation": True,
        "bgcolor": "#e9f8c1",
        "border": "#0b5809"
    }
}


class MainWindow(QMainWindow):

    # Signals
    stateChanged = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Hodes Pytomator")
        self.setWindowIcon(QIcon(":/icons/app_64.png"))
        # Window size (default, may be overridden by saved geometry)
        self.resize(800, 600)
        self._restore_window_geometry()

        # ── Core services ──────────────────────────────────
        self.project_manager = ProjectManager()
        self.script_runner = ScriptRunner()
        self.capture_manager = CaptureManager(self.project_manager, self)
        self.capture_manager.set_main_window(self)

        # Register the project manager with the automator API so import_script works
        automator_api.set_project_manager(self.project_manager)

        self.script_runner.on("started", lambda: self.on_runner_state_change(True))
        self.script_runner.on("finished", lambda: self.on_runner_state_change(False))
        self.script_runner.on("interrupted", lambda: self.on_runner_state_change(False))

        # ── Tabs ───────────────────────────────────────────
        self.tabs = QTabWidget()

        # Tab 0: Project
        self.project_frame = ProjectFrame(self.project_manager)
        self.project_frame.project_opened.connect(self._on_project_opened)
        self.project_frame.project_closed.connect(self._on_project_closed)
        self.tabs.addTab(self.project_frame, "Project")
        self.tabs.setTabIcon(0, qta.icon("fa6s.folder"))

        # Tab 1: Editor
        self.editor_frame = EditorFrame(self.script_runner, self.project_manager)
        self.tabs.addTab(self.editor_frame, "Script Editor")
        self.tabs.setTabIcon(1, qta.icon("fa6s.code"))

        # Tab 2: Settings
        self.settings_frame = SettingsFrame(self.project_manager)
        self.tabs.addTab(self.settings_frame, "Settings")
        self.tabs.setTabIcon(2, qta.icon("fa5s.cog"))

        # Tab 3: Templates
        self.templates_frame = TemplatesFrame(self.project_manager, self.capture_manager)
        self.tabs.addTab(self.templates_frame, "Templates")
        self.tabs.setTabIcon(3, qta.icon("fa6s.image"))

        # Tab 4: About
        self.tabs.addTab(AboutFrame(), "About")
        self.tabs.setTabIcon(4, qta.icon("mdi.help-circle"))

        # ── Status bar ─────────────────────────────────────
        self._current_icon = None
        self._current_color = None
        self._icon_anim_timer = QTimer(self)
        self._icon_anim_timer.setInterval(40)  # ~25 FPS
        self._icon_anim_timer.timeout.connect(self._update_status_icon)

        self.status_indicator = QLabel()
        self.status_indicator.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.status_indicator.setContentsMargins(6, 0, 6, 0)
        self.statusBar().addPermanentWidget(self.status_indicator)
        self.stateChanged.connect(self._state_changed)
        self.set_state('stopped')

        self.setCentralWidget(self.tabs)

        # ── Project indicator in status bar ────────────────
        self.project_label = QLabel("No project")
        self.project_label.setContentsMargins(6, 0, 6, 0)
        self.statusBar().addPermanentWidget(self.project_label)

        self.project_manager.on("project_loaded", self._update_project_status)
        self.project_manager.on("project_closed", self._update_project_status)
        self.project_manager.on("project_saved", self._update_project_status)
        self._update_project_status()

    # ------------------------------------------------------------------
    # Project lifecycle
    # ------------------------------------------------------------------

    def _on_project_opened(self):
        """When a project is opened, switch to the editor tab."""
        self.tabs.setCurrentIndex(1)  # Editor tab

    def _on_project_closed(self):
        """When a project is closed, switch back to the project tab."""
        self.tabs.setCurrentIndex(0)  # Project tab

    def _update_project_status(self):
        """Update the project label in the status bar."""
        if self.project_manager.is_project_open:
            name = self.project_manager.project.name if self.project_manager.project else "project"
            path = self.project_manager.project_path
            short_path = str(path) if path else "(unsaved)"
            self.project_label.setText(f"Project: {name} [{short_path}]")
        else:
            self.project_label.setText("No project")

    # ------------------------------------------------------------------
    # Runner state
    # ------------------------------------------------------------------

    def on_runner_state_change(self, is_running: bool):
        if is_running:
            self.set_state('running')
        else:
            self.set_state('stopped')

    def set_state(self, state: str):
        self.stateChanged.emit(state)

    def _update_status_icon(self):
        if not self._current_icon:
            return

        icon = qta.icon(
            self._current_icon,
            color=self._current_color,
            animation=self._current_animation
        )
        self.status_indicator.setPixmap(icon.pixmap(24, 24))

    def _state_changed(self, state: str):
        current_state = APP_STATES[state]
        bgcolor = current_state.get('bgcolor')
        border = current_state.get('border')

        self._current_icon = current_state['icon']
        self._current_color = current_state['color']

        if current_state.get('animation'):
            if not hasattr(self, "_spin_anim"):
                self._spin_anim = qta.Spin(self, interval=5)
            self._current_animation = self._spin_anim
            self._icon_anim_timer.start()
        else:
            self._current_animation = None
            self._icon_anim_timer.stop()

        style = f"""
            QStatusBar {{
                background-color: {bgcolor};
                color: {self._current_color.name()};
                border-top: 3px solid {border};
            }}
        """
        icon = qta.icon(
            self._current_icon,
            color=self._current_color,
            animation=self._current_animation
        )
        title = f"Script execution is: {current_state.get('title')}"
        self.status_indicator.setPixmap(icon.pixmap(24, 24))
        self.status_indicator.setToolTip(title)
        if getattr(self, "_last_style", None) != style:
            self.statusBar().setStyleSheet(style)
            self._last_style = style
        self.statusBar().showMessage(title)

    # ------------------------------------------------------------------
    # Window geometry persistence
    # ------------------------------------------------------------------

    def _save_window_geometry(self):
        """Salva posição, tamanho e estado da janela via QSettings."""
        settings = QSettings("Hodes", "Pytomator")
        settings.setValue("window/geometry", self.saveGeometry())
        settings.setValue("window/state", self.saveState())
        settings.setValue("window/maximized", self.isMaximized())
        if not self.isMaximized():
            settings.setValue("window/position", self.pos())
            settings.setValue("window/size", self.size())

    def _restore_window_geometry(self):
        """Restaura geometria da janela, validando se está visível na tela."""
        settings = QSettings("Hodes", "Pytomator")

        geometry = settings.value("window/geometry")
        maximized = settings.value("window/maximized", False, type=bool)

        if geometry is not None:
            self.restoreGeometry(geometry)

            # Validar se a janela está visível em pelo menos um monitor
            screen = QGuiApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                window_geometry = self.frameGeometry()

                # Se a janela estiver completamente fora da tela, resetar
                if not screen_geometry.intersects(window_geometry):
                    self.resize(600, 800)
                    self._center_on_screen()

            if maximized:
                self.showMaximized()
        else:
            # Primeira execução: centralizar na tela
            self._center_on_screen()

    def _center_on_screen(self):
        """Centraliza a janela na tela primária."""
        screen = QGuiApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            x = (screen_geometry.width() - self.width()) // 2
            y = (screen_geometry.height() - self.height()) // 2
            self.move(x, y)

    def closeEvent(self, event):
        self._save_window_geometry()
        if self.script_runner.is_running():
            self.script_runner.stop()
        event.accept()
