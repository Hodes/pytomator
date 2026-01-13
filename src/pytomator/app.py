import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from pytomator.ui import MainWindow

import pytomator.resources.resources_rc

def main():
    app = QApplication(sys.argv)
    
    icon = QIcon()
    icon.addFile(":/icons/app_16.png")
    icon.addFile(":/icons/app_32.png")
    icon.addFile(":/icons/app_48.png")
    icon.addFile(":/icons/app_64.png")
    icon.addFile(":/icons/app_128.png")
    icon.addFile(":/icons/app_256.png")
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
