#!/usr/bin/env python3
import sys
import os

# Suppress stderr noise from appimaged/AppImageLauncher scanning ~/Applications.
# Real errors surface in the app's live log via the worker protocol.
sys.stderr = open(os.devnull, 'w')

from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main() -> None:
    dist_enabled = '--dist' in sys.argv

    app = QApplication(sys.argv)
    app.setApplicationName("XeroPi4")
    app.setOrganizationName("TechXero")

    window = MainWindow(dist_enabled=dist_enabled)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
