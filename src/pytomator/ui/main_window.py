from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QLabel
)
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
import qtawesome as qta

from pytomator.ui.about_frame import AboutFrame
from pytomator.ui.editor_frame import EditorFrame
from pytomator.core.script_runner import ScriptRunner
from pytomator.ui.settings_frame import SettingsFrame

APP_STATES = {
    "stopped":{
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
        
        self.setCentralWidget(tabs)

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
        
    
    def closeEvent(self, event):
        if self.script_runner.is_running():
            self.script_runner.stop()
        event.accept()
