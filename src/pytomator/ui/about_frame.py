
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTextBrowser
)
from PyQt6.QtCore import Qt

from pytomator.ui.api_doc_generator import generate_api_html
from pytomator import __version__
from pytomator.build_info import BUILD_YEAR

class AboutFrame(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()
        
        api_doc_browser = QTextBrowser()
        api_doc_browser.setReadOnly(True)
        api_doc_browser.setHtml(generate_api_html())
        
        about_label = QLabel(f"Pytomator\nVersion {__version__}\n© {BUILD_YEAR} Hodes")
        about_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(about_label)
        layout.addWidget(api_doc_browser)
        
        
        self.setLayout(layout)
