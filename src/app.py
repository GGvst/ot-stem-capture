"""Application entry point"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from .main_window import MainWindow


def main():
    """Main entry point"""
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("OT Stem Capture")
    app.setOrganizationName("OT Tools")

    # Set dark palette
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
