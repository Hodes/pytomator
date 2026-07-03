import faulthandler
import logging
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from pytomator.ui import MainWindow

import pytomator.resources.resources_rc

def _configure_diagnostics() -> object:
    """Keep a persistent record of Python errors and native crashes."""
    log_dir = Path.home() / ".pytomator" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "pytomator.log"
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    crash_stream = (log_dir / "crash.log").open("a", encoding="utf-8")
    faulthandler.enable(crash_stream, all_threads=True)

    def log_unhandled(exc_type, exc_value, exc_traceback):
        logging.getLogger(__name__).critical(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = log_unhandled
    return crash_stream


def main():
    crash_stream = _configure_diagnostics()
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
    exit_code = app.exec()
    crash_stream.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
