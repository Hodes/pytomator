
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextBrowser
)
from PyQt6.QtCore import Qt

from pytomator.ui.api_doc_generator import generate_api_html
from pytomator import __version__

class AboutFrame(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        
        api_doc_browser = QTextBrowser()
        api_doc_browser.setReadOnly(True)
        api_doc_browser.setHtml(generate_api_html())
        
        about_label = QLabel("Pytomator\nVersion " + __version__ + "\n© 2025 Hodes")
        about_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(about_label)
        layout.addWidget(api_doc_browser)
        
        
        self.setLayout(layout)