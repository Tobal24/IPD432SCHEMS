"""
Entry point for the ELO212 & IPD432 Digital Design Suite.
Launch with:
    python main.py
"""
from __future__ import annotations

import sys
import os

# Ensure current workspace is on Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont
from app.gui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("ELO212 / IPD432 Digital Design Suite")
    app.setOrganizationName("USM Digital Systems")

    # Clean, modern readable font
    font = QFont("Segoe UI", 9)
    app.setFont(font)

    # Modern Fusion style
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
