
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel
)
from PyQt6.QtCore import Qt

from pytomator import __version__

class AboutFrame(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        about_label = QLabel("Pytomator\nVersion " + __version__ + "\n© 2025 Hodes")
        about_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(about_label)
        self.setLayout(layout)